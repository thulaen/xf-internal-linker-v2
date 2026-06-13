"""GlitchTip performance-transaction → AutoIssue picker.

Closes the last GlitchTip gap: the existing ``glitchtip_picker`` promotes
*errors* (events that raised), but a slow endpoint or background job can get
progressively slower WITHOUT ever raising — so it never reaches AutoIssues.

GlitchTip exposes aggregated performance data at its own
``/api/0/organizations/<org>/transaction-groups/`` endpoint (one row per
transaction name carrying ``p95`` / ``avgDuration`` / ``count`` in
milliseconds). This picker fetches those groups, keeps the ones whose ``p95``
exceeds the slow threshold, sorts them client-side, and files each over the
threshold as an AutoIssue tagged ``source='glitchtip'`` under the
``performance`` category. NOTE: the Sentry "organization events" discover
endpoint is NOT implemented by GlitchTip (it returns 404), and the
transaction-groups endpoint rejects server-side ``sort`` (HTTP 422), so we
fetch the default page and rank by ``p95`` in Python.

Shape mirrors ``slow_query_picker.py`` exactly:
  * the HTTP fetch is isolated behind ``_fetch_glitchtip_transactions`` (never
    raises — returns [] when env vars are unset or GlitchTip is unreachable),
    so the pure pipeline runs over already-fetched dicts and tests need no
    live GlitchTip;
  * filing goes through the cross-source ``upsert_dedup`` helper, so a slow
    transaction caught here merges onto one AutoIssue row (no duplicates) and
    a re-run of the same transaction reports ``updated``/``merged`` instead of
    creating a clone.
"""

from __future__ import annotations

import hashlib
import logging
import os
from dataclasses import dataclass

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint

logger = logging.getLogger(__name__)

# Surface only transactions whose p95 duration exceeds this threshold. Matches
# the slow-query picker's medium band so the two perf pickers agree on "slow".
_MIN_DURATION_MS = 250.0
_MAX_PER_RUN = 10
_REQUEST_TIMEOUT = 15  # seconds — same as the GlitchTip error-sync fetch.

# Field names returned by GlitchTip's transaction-groups endpoint (NOT the
# Sentry discover-events aliases — GlitchTip serves its own performance API).
_FIELD_TRANSACTION = "transaction"
_FIELD_DURATION = "p95"
_FIELD_COUNT = "count"
_FIELD_OP = "op"

# Only USER-FACING request transactions are actionable as "slow endpoints".
# GlitchTip tags each transaction-group with an ``op``: ``http.server`` (a
# backend API endpoint) and ``pageload`` (a frontend page load) are user-facing.
# Everything else — ``queue.task.celery`` and empty-op ``run/...`` background
# jobs, raw ``db`` spans — is expected to run long and is excluded, so the
# picker surfaces slow endpoints instead of expected-slow background work.
_USER_FACING_OPS = frozenset({"http.server", "pageload"})


@dataclass(frozen=True)
class SlowTransaction:
    """One performance transaction after thresholding."""

    transaction: str
    duration_ms: float
    count: int
    op: str = ""
    endpoint: str = ""


def _glitchtip_perf_env() -> tuple[str, str, str, str]:
    """Return (api_url, token, org_slug, project_slug). All four blank when unset.

    Reuses the SAME four env vars the GlitchTip error-sync task reads, so a
    project already wired for GlitchTip errors gets perf transactions for free.
    """
    return (
        os.environ.get("GLITCHTIP_API_URL", "").rstrip("/"),
        os.environ.get("GLITCHTIP_API_TOKEN", ""),
        os.environ.get("GLITCHTIP_ORG_SLUG", ""),
        os.environ.get("GLITCHTIP_PROJECT_SLUG", ""),
    )


def _fetch_glitchtip_transactions(*, limit: int) -> list[dict]:
    """GET the slowest transactions from the Sentry-compatible events endpoint.

    Never raises: returns [] when env vars are unset or GlitchTip is
    unreachable, so a project without GlitchTip configured sees a clean no-op
    (mirrors how slow_query_picker swallows a missing pg_stat_statements view).
    """
    import requests

    api_url, token, org, proj = _glitchtip_perf_env()
    if not all([api_url, token, org, proj]):
        return []
    try:
        # GlitchTip's transaction-groups endpoint returns a bare JSON list of
        # aggregated transactions (one per name) for the org. It rejects
        # server-side sort/project params (HTTP 422), so we take the default
        # page and rank client-side. `limit` is unused at the wire level but
        # kept in the signature for the caller's intent + future pagination.
        response = requests.get(
            f"{api_url}/api/0/organizations/{org}/transaction-groups/",
            headers={"Authorization": f"Bearer {token}"},
            timeout=_REQUEST_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
    except requests.RequestException as exc:
        logger.warning("[glitchtip_perf_picker] fetch failed: %s", exc)
        return []
    except ValueError as exc:
        logger.warning("[glitchtip_perf_picker] response not JSON: %s", exc)
        return []
    # Sentry wraps rows in {"data": [...]}; tolerate a bare list too.
    if isinstance(payload, dict):
        return list(payload.get("data") or [])
    return list(payload or [])


def _coerce_float(value: object) -> float:
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0.0


def _coerce_int(value: object) -> int:
    try:
        return int(float(value))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return 0


_HTTP_METHODS = frozenset(
    {"GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS", "TRACE", "CONNECT"}
)


def _normalize_transaction_name(name: str) -> str:
    """Strip leading HTTP-method tokens so each endpoint collapses to one row.

    GlitchTip occasionally names an HTTP transaction with the request method
    prefixed — sometimes twice (e.g. ``POST POST /api/x/``) — while also
    tracking a bare ``/api/x/`` group, i.e. two rows for one endpoint. Dropping
    the leading method token(s) maps both onto the same path, so they share a
    dedup key and ``upsert_dedup`` merges them into a single AutoIssue.
    """
    parts = name.split()
    while len(parts) > 1 and parts[0].upper() in _HTTP_METHODS:
        parts.pop(0)
    return " ".join(parts)


def _parse_transactions(rows: list[dict], *, min_ms: float) -> list[SlowTransaction]:
    """Map raw GlitchTip transaction-group rows to SlowTransaction.

    Keeps only USER-FACING transactions (``op`` in ``_USER_FACING_OPS``) that
    are also slower than ``min_ms``. Background jobs and internal spans are
    excluded so the picker surfaces actionable slow endpoints, not the
    expected-slow Celery jobs / scans / benchmarks.
    """
    out: list[SlowTransaction] = []
    for row in rows:
        op = str(row.get(_FIELD_OP) or "").strip()
        if op not in _USER_FACING_OPS:
            continue
        name = _normalize_transaction_name(str(row.get(_FIELD_TRANSACTION) or ""))
        duration = _coerce_float(row.get(_FIELD_DURATION))
        if not name or duration < min_ms:
            continue
        out.append(
            SlowTransaction(
                transaction=name[:300],
                duration_ms=duration,
                count=_coerce_int(row.get(_FIELD_COUNT)),
                op=op,
                endpoint=name[:300],
            )
        )
    return out


def _severity_for(t: SlowTransaction) -> str:
    """Map p95 duration onto severity bands — slower means higher severity."""
    if t.duration_ms >= 5000:
        return AutoIssue.SEVERITY_CRITICAL
    if t.duration_ms >= 1000:
        return AutoIssue.SEVERITY_HIGH
    if t.duration_ms >= 250:
        return AutoIssue.SEVERITY_MEDIUM
    return AutoIssue.SEVERITY_LOW


def _stable_external_id(t: SlowTransaction) -> str:
    # SHA1 is non-security here (deduplication fingerprint, not auth).
    raw = f"gt-perf::{t.transaction}".encode()
    return hashlib.sha1(raw, usedforsecurity=False).hexdigest()[:16]


def _format_title(t: SlowTransaction) -> str:
    one_line = " ".join(t.transaction.split())
    return f"Slow transaction: {one_line[:90]} p95 {t.duration_ms:.0f}ms ({t.count} events)"


def _priority_score(t: SlowTransaction, max_duration: float) -> float:
    """Normalise duration to [0, 1] so the picker ranks by how slow it is."""
    if max_duration <= 0:
        return 0.0
    return min(1.0, t.duration_ms / max_duration)


def _upsert_transaction(t: SlowTransaction, priority: float) -> str:
    """Upsert a single slow transaction through the cross-source dedup helper."""
    title = _format_title(t)
    canonical = canonical_fingerprint(title, "")
    description = (
        f"GlitchTip performance transaction `{t.transaction}` is slow: "
        f"p95 duration {t.duration_ms:.0f} ms over {t.count} events.\n"
        f"This endpoint/job never raised an exception, so it is invisible to "
        f"the GlitchTip error feed — it surfaces here as a performance issue. "
        f"Profile the transaction in GlitchTip's Performance view to find the "
        f"slow span."
    )
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_GLITCHTIP,
        external_id=_stable_external_id(t),
        fingerprint=_stable_external_id(t),
        title=title,
        description=description,
        affected_files=[],  # transaction span is in GlitchTip, not a file
        severity=_severity_for(t),
        priority_score=priority,
        occurrence_count=max(t.count, 1),
        category_key="performance",
    )
    return outcome


def pick_slowest_glitchtip_transactions(*, limit: int = _MAX_PER_RUN) -> dict:
    """Top-K slowest GlitchTip transactions → AutoIssue (with cross-source dedup)."""
    rows = _fetch_glitchtip_transactions(limit=limit * 5)
    transactions = _parse_transactions(rows, min_ms=_MIN_DURATION_MS)
    if not transactions:
        return {
            "status": "ok",
            "fetched": 0,
            "promoted": 0,
            "created": 0,
            "merged": 0,
            "updated": 0,
        }

    transactions.sort(key=lambda t: t.duration_ms, reverse=True)
    max_duration = max(t.duration_ms for t in transactions)
    counts = {"created": 0, "merged": 0, "updated": 0}
    for t in transactions[:limit]:
        outcome = _upsert_transaction(t, _priority_score(t, max_duration))
        counts[outcome] = counts.get(outcome, 0) + 1

    logger.info(
        "[auto_issues.glitchtip_perf_picker] fetched=%d created=%d merged=%d updated=%d",
        len(transactions), counts["created"], counts["merged"], counts["updated"],
    )
    return {
        "status": "ok",
        "fetched": len(transactions),
        "promoted": sum(counts.values()),
        **counts,
    }
