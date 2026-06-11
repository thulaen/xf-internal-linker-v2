"""Loki -> AutoIssue picker.

Two complementary detectors that read container stdout logs from Loki
via LogQL and surface noisy patterns as ``AutoIssue(source='loki')``
rows:

  - ``pick_loki_hot_patterns`` — repeated WARN / ERROR / Traceback
    lines whose normalized fingerprint occurs >= ``loki.hot_pattern_min_count``
    times in the scan window (default 24 h). Works from day one — as
    long as Alloy is shipping logs and ANY error pattern is repeating,
    this fires.
  - ``pick_loki_warn_bursts`` — per-container WARN/ERROR rate spikes:
    last-hour count vs 24 h average, promoted when the multiple
    >= ``loki.warn_burst_multiplier`` (default 3x). Needs >= 24 h of
    log history to produce useful findings; no-ops cleanly otherwise.

Both use disjoint fingerprint prefixes (``loki:hot::`` vs
``loki:burst::``) so they never collide on the
``(source, external_id)`` unique constraint. Both write through the
existing ``upsert_dedup`` / ``score_candidate`` plumbing — same as the
GlitchTip and Pyroscope pickers.

Added 2026-05-10 per plan
``docs/plans/does-adding-qodana-make-swift-wall.md`` Stream 4.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.scoring import Candidate, score_candidate

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 20.0
_MAX_PER_RUN = 10

# Patterns stripped during fingerprinting so "ERROR connection failed
# at 10:11:12" and "ERROR connection failed at 10:11:13" collapse to
# the same fingerprint. KISS — half a dozen common cases, not a full
# log parser.
_NORMALIZE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    # ISO-8601 timestamps: 2026-05-10 08:48:21,488 / 2026-05-10T08:48:21
    (re.compile(r"\b\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:[.,]\d+)?(?:Z|[+-]\d{2}:?\d{2})?\b"), "<TS>"),
    # Square-bracketed timestamps: [10/Jun/2025 22:11:33]
    (re.compile(r"\[\d{1,2}/[A-Za-z]{3,9}/\d{4}[ :]\d{1,2}:\d{2}:\d{2}\]"), "<TS>"),
    # UUIDs — must come BEFORE PID stripper so the first 8-char hex
    # group of a UUID isn't accidentally replaced as a "long int".
    (re.compile(r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"), "<UUID>"),
    # Hex addresses: 0xdeadbeef, 0x7f8a3b2c0
    (re.compile(r"0x[0-9a-fA-F]+"), "<HEX>"),
    # Traceback "line 123" -> "line <N>"
    (re.compile(r"\bline \d+\b"), "line <N>"),
    # PIDs / TIDs / Python thread IDs (5+ digit ints — common in log prefixes)
    (re.compile(r"\b\d{5,}\b"), "<N>"),
)

# What counts as a "noisy" line. Loki LogQL filter passed to
# `_fetch_loki_lines`. Case-insensitive substring match — we tried
# `\\b...\\b` word boundaries but Loki's regex engine returned 0 hits
# in practice, and the downstream normalization + count threshold
# already filters out incidental substring matches like "error_count=0"
# (their content varies, so they never accumulate to threshold).
_NOISE_FILTER = '|~ "(?i)(error|warn|warning|critical|exception|traceback)" !~ "database \\"test_xf_linker\\" already exists" !~ "timestamp too old" !~ "database \\"test_xf_linker\\" is being accessed" !~ "current transaction is aborted"'


@dataclass(frozen=True)
class LokiCandidate:
    """One promotable pattern (hot pattern OR burst)."""

    kind: str                  # "hot_pattern" | "warn_burst"
    fingerprint: str           # "loki:hot::<sha>" or "loki:burst::<sha>"
    sample_line: str
    container_name: str
    occurrence_count: int
    extra: str                 # human-readable detail line for the description


# --- Helpers ---------------------------------------------------------


def _read_loki_settings() -> dict[str, Any]:
    """Read tunable thresholds from AppSetting with safe fallbacks."""
    from apps.core.models import AppSetting

    keys = (
        "loki.api_url",
        "loki.scan_window_seconds",
        "loki.hot_pattern_min_count",
        "loki.warn_burst_multiplier",
        "loki.max_lines_per_query",
    )
    rows = {
        s.key: s.value
        for s in AppSetting.objects.filter(key__in=keys).only("key", "value")
    }
    return {
        "api_url": rows.get("loki.api_url", "http://loki:3100"),
        "scan_window_seconds": _safe_int(rows.get("loki.scan_window_seconds"), 86400),
        "hot_pattern_min_count": _safe_int(rows.get("loki.hot_pattern_min_count"), 10),
        "warn_burst_multiplier": _safe_float(rows.get("loki.warn_burst_multiplier"), 3.0),
        "max_lines_per_query": _safe_int(rows.get("loki.max_lines_per_query"), 5000),
    }


def _safe_int(raw, fallback: int) -> int:
    try:
        return int(raw) if raw is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _safe_float(raw, fallback: float) -> float:
    try:
        return float(raw) if raw is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _normalize_line(line: str) -> str:
    """Strip volatile content so similar log lines share a fingerprint.

    Keeps the line's structural shape so an operator reading the
    fingerprint can guess the source pattern at a glance.
    """
    out = line
    for pattern, replacement in _NORMALIZE_PATTERNS:
        out = pattern.sub(replacement, out)
    # Squeeze multiple spaces.
    out = re.sub(r"\s+", " ", out).strip()
    # Cap to a reasonable size so a 20 KB stack trace doesn't bloat the
    # fingerprint or the AutoIssue.title field.
    return out[:512]


def _stable_fingerprint(prefix: str, normalized: str) -> str:
    raw = f"{prefix}::{normalized}"
    return f"{prefix}::{hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]}"


def _is_stack_container(container_name: str) -> bool:
    return container_name.startswith("xf_linker_")


def _fetch_loki_lines(
    api_url: str, *, query: str, window_s: int, limit: int
) -> list[tuple[str, str]]:
    """Pull raw log lines from Loki. Returns (container_name, line) tuples.

    No-ops cleanly (returns []) on any HTTP failure.
    """
    now_ns = int(timezone.now().timestamp() * 1_000_000_000)
    start_ns = now_ns - window_s * 1_000_000_000
    params = {
        "query": query,
        "start": start_ns,
        "end": now_ns,
        "limit": limit,
        "direction": "backward",
    }
    try:
        r = requests.get(
            f"{api_url.rstrip('/')}/loki/api/v1/query_range",
            params=params,
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[loki_picker] query_range failed: %s", exc)
        return []
    streams = (body.get("data") or {}).get("result") or []
    out: list[tuple[str, str]] = []
    for stream in streams:
        labels = stream.get("stream") or {}
        container = labels.get("container_name") or labels.get("service") or "unknown"
        for ts_ns, line in stream.get("values") or []:
            out.append((container, line))
    return out


# --- Hot patterns ----------------------------------------------------


def _gather_hot_patterns(
    api_url: str, *, window_s: int, min_count: int, max_lines: int
) -> list[LokiCandidate]:
    """Group log lines by normalized fingerprint; surface ones that recur."""
    query = '{container_name=~".+"} ' + _NOISE_FILTER
    rows = _fetch_loki_lines(
        api_url, query=query, window_s=window_s, limit=max_lines
    )
    if not rows:
        return []

    # Group by normalized fingerprint -> (count, sample_line, container).
    grouped: dict[str, dict[str, Any]] = {}
    for container, line in rows:
        if not _is_stack_container(container):
            continue
        normalized = _normalize_line(line)
        if not normalized:
            continue
        bucket = grouped.setdefault(
            normalized,
            {"count": 0, "sample": line, "container": container},
        )
        bucket["count"] += 1

    out: list[LokiCandidate] = []
    for normalized, data in grouped.items():
        if data["count"] < min_count:
            continue
        out.append(
            LokiCandidate(
                kind="hot_pattern",
                fingerprint=_stable_fingerprint("loki:hot", normalized),
                sample_line=str(data["sample"])[:512],
                container_name=str(data["container"]),
                occurrence_count=int(data["count"]),
                extra=(
                    f"Pattern occurred {data['count']}x in the last "
                    f"{window_s // 3600} h across container "
                    f"{data['container']}."
                ),
            )
        )
    return out


# --- Warn bursts -----------------------------------------------------


def _container_count_over_time(
    api_url: str, *, container: str, range_s: int
) -> int:
    """Run a count_over_time LogQL query and return the integer count."""
    query = (
        f'sum(count_over_time({{container_name="{container}"}} '
        f'{_NOISE_FILTER} [{range_s}s]))'
    )
    params = {
        "query": query,
        "time": int(timezone.now().timestamp() * 1_000_000_000),
    }
    try:
        r = requests.get(
            f"{api_url.rstrip('/')}/loki/api/v1/query",
            params=params,
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[loki_picker] count_over_time failed for %s: %s", container, exc)
        return 0
    result = (body.get("data") or {}).get("result") or []
    if not result:
        return 0
    try:
        return int(float(result[0]["value"][1]))
    except (KeyError, IndexError, TypeError, ValueError):
        return 0


def _list_active_containers(api_url: str) -> list[str]:
    """Return container_name values seen in the last hour."""
    try:
        r = requests.get(
            f"{api_url.rstrip('/')}/loki/api/v1/label/container_name/values",
            params={
                "start": int(
                    (timezone.now().timestamp() - 3600) * 1_000_000_000
                ),
                "end": int(timezone.now().timestamp() * 1_000_000_000),
            },
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[loki_picker] label values fetch failed: %s", exc)
        return []
    return list(body.get("data") or [])


def _gather_warn_bursts(
    api_url: str, *, multiplier: float
) -> list[LokiCandidate]:
    out: list[LokiCandidate] = []
    for container in _list_active_containers(api_url):
        if not _is_stack_container(container):
            continue
        last_hour = _container_count_over_time(
            api_url, container=container, range_s=3600
        )
        last_24h = _container_count_over_time(
            api_url, container=container, range_s=86400
        )
        if last_24h <= 0 or last_hour <= 0:
            continue
        baseline_per_hour = last_24h / 24.0
        if baseline_per_hour <= 0:
            continue
        ratio = last_hour / baseline_per_hour
        if ratio < multiplier:
            continue
        out.append(
            LokiCandidate(
                kind="warn_burst",
                fingerprint=_stable_fingerprint(
                    "loki:burst", f"{container}::{int(ratio)}"
                ),
                sample_line=f"{container}: {last_hour} WARN/ERROR in last 1h",
                container_name=container,
                occurrence_count=last_hour,
                extra=(
                    f"Last-hour rate {last_hour} WARN/ERROR vs 24 h "
                    f"average {baseline_per_hour:.1f}/h "
                    f"(ratio {ratio:.1f}x)."
                ),
            )
        )
    return out


# --- Common upsert + scoring ----------------------------------------


def _candidate_for_score(lc: LokiCandidate, max_blast: float) -> Candidate:
    severity = (
        AutoIssue.SEVERITY_HIGH
        if lc.kind == "warn_burst" and lc.occurrence_count > 100
        else AutoIssue.SEVERITY_MEDIUM
    )
    return Candidate(
        source=AutoIssue.SOURCE_LOKI,
        external_id=lc.fingerprint,
        fingerprint=lc.fingerprint,
        severity=severity,
        last_seen=timezone.now(),
        blast_observed=float(lc.occurrence_count),
        blast_max=float(max(max_blast, 1)),
        num_affected_files=0,
    )


def _upsert_loki_row(score: float, lc: LokiCandidate) -> str:
    title = (
        f"Loki: [{lc.kind}] "
        + (lc.sample_line[:160] if lc.kind == "hot_pattern" else lc.sample_line[:200])
    )
    description = (
        f"{lc.extra}\n\n"
        f"Container: `{lc.container_name}`\n"
        f"Sample line: ```{lc.sample_line[:480]}```"
    )
    canonical = canonical_fingerprint(lc.sample_line[:200], lc.container_name)
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_LOKI,
        external_id=lc.fingerprint,
        fingerprint=lc.fingerprint,
        title=title[:512],
        description=description[:4000],
        affected_files=[],
        severity=(
            AutoIssue.SEVERITY_HIGH
            if lc.kind == "warn_burst" and lc.occurrence_count > 100
            else AutoIssue.SEVERITY_MEDIUM
        ),
        priority_score=float(score),
        occurrence_count=lc.occurrence_count,
    )
    return outcome


def _score_and_promote(
    cands: list[LokiCandidate], *, limit: int
) -> int:
    if not cands:
        return 0
    max_blast = max(c.occurrence_count for c in cands)
    scored = [
        (score_candidate(_candidate_for_score(lc, max_blast)), lc)
        for lc in cands
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    promoted = 0
    for score, lc in scored[:limit]:
        _upsert_loki_row(score, lc)
        promoted += 1
    return promoted


# --- Public API ------------------------------------------------------


def pick_loki_hot_patterns(*, limit: int = _MAX_PER_RUN) -> dict:
    """Surface repeated WARN/ERROR patterns from Loki as AutoIssues."""
    settings = _read_loki_settings()
    cands = _gather_hot_patterns(
        settings["api_url"],
        window_s=settings["scan_window_seconds"],
        min_count=settings["hot_pattern_min_count"],
        max_lines=settings["max_lines_per_query"],
    )
    promoted = _score_and_promote(cands, limit=limit)
    logger.info(
        "[loki_picker.hot_patterns] candidates=%d promoted=%d "
        "min_count=%d window_s=%d",
        len(cands), promoted,
        settings["hot_pattern_min_count"], settings["scan_window_seconds"],
    )
    return {
        "status": "ok",
        "patterns_found": len(cands),
        "promoted": promoted,
    }


def pick_loki_warn_bursts(*, limit: int = _MAX_PER_RUN) -> dict:
    """Surface 1h vs 24h rate spikes per container as AutoIssues."""
    settings = _read_loki_settings()
    cands = _gather_warn_bursts(
        settings["api_url"], multiplier=settings["warn_burst_multiplier"]
    )
    promoted = _score_and_promote(cands, limit=limit)
    logger.info(
        "[loki_picker.warn_bursts] candidates=%d promoted=%d multiplier=%.1f",
        len(cands), promoted, settings["warn_burst_multiplier"],
    )
    return {
        "status": "ok",
        "bursts_found": len(cands),
        "promoted": promoted,
    }


def pick_loki_findings(*, limit: int = _MAX_PER_RUN) -> dict:
    """Convenience wrapper — runs both detectors in one call."""
    hot = pick_loki_hot_patterns(limit=limit)
    bursts = pick_loki_warn_bursts(limit=limit)
    return {"hot_patterns": hot, "warn_bursts": bursts}
