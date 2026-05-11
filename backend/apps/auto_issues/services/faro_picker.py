"""Faro -> AutoIssue picker.

Faro is Grafana's frontend Real User Monitoring SDK. The browser ships
JS errors + Web Vitals + session events to the Alloy ``faro.receiver``
block, which forwards them to Loki labelled
``{service="frontend", source="faro"}``. This picker queries those Loki
streams via LogQL and promotes recurring problems as
``AutoIssue(source='faro')`` rows.

Two detectors with disjoint fingerprint prefixes so they never collide
on the ``(source, external_id)`` unique constraint:

  - ``pick_faro_error_clusters`` — JS errors / exceptions whose
    normalized fingerprint occurs at least
    ``faro.error_min_count`` times in the scan window.
  - ``pick_faro_webvital_breaches`` — sessions with LCP / INP / CLS over
    per-metric thresholds, grouped by route.

Both feed through the existing ``upsert_dedup`` plumbing so a JS error
also captured by GlitchTip (Sentry SDK) collapses into one canonical
row via ``source_observations``.

Added 2026-05-11 per plan
``~/.claude/plans/objective-deploy-and-integrate-zany-bee.md`` Stream 5.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.loki_picker import _NORMALIZE_PATTERNS
from apps.auto_issues.services.scoring import Candidate, score_candidate

logger = logging.getLogger(__name__)

_REQUEST_TIMEOUT = 20.0
_MAX_PER_RUN = 10

# Faro events ship as JSON log lines tagged ``source="faro"``. The error
# events have ``type=exception`` or ``type=error``; web-vital events have
# ``type=measurement`` with ``name`` in {"largest_contentful_paint",
# "interaction_to_next_paint", "cumulative_layout_shift"}.
_FARO_LABEL = '{service="frontend", source="faro"}'
_ERROR_FILTER = '|~ "(?i)(error|exception)"'

# Sessions over this many breach samples count as a hot route. Matches
# the Loki picker's "at least 10 occurrences" heuristic so the two
# detectors stay numerically consistent.
_WEBVITAL_MIN_SAMPLES = 10


@dataclass(frozen=True)
class FaroCandidate:
    """One promotable Faro finding (error cluster OR web-vital breach)."""

    kind: str  # "error_cluster" | "webvital_breach"
    fingerprint: str
    sample_message: str
    route_or_metric: str
    occurrence_count: int
    extra: str  # human-readable description detail


# --- Helpers ---------------------------------------------------------


def _read_faro_settings() -> dict[str, Any]:
    """Read tunable thresholds from AppSetting with safe fallbacks."""
    from apps.core.models import AppSetting

    keys = (
        "faro.collector_url",
        "faro.session_sample_rate",
        "faro.error_min_count",
        "faro.web_vitals_threshold_lcp_ms",
        "faro.web_vitals_threshold_inp_ms",
        "faro.web_vitals_threshold_cls",
        # Reuse loki.api_url since faro events live in Loki streams.
        "loki.api_url",
        "loki.scan_window_seconds",
        "loki.max_lines_per_query",
    )
    rows = {
        s.key: s.value
        for s in AppSetting.objects.filter(key__in=keys).only("key", "value")
    }
    return {
        "loki_api_url": rows.get("loki.api_url", "http://loki:3100"),
        "scan_window_seconds": _safe_int(rows.get("loki.scan_window_seconds"), 86400),
        "max_lines_per_query": _safe_int(rows.get("loki.max_lines_per_query"), 5000),
        "error_min_count": _safe_int(rows.get("faro.error_min_count"), 5),
        "lcp_threshold_ms": _safe_int(rows.get("faro.web_vitals_threshold_lcp_ms"), 2500),
        "inp_threshold_ms": _safe_int(rows.get("faro.web_vitals_threshold_inp_ms"), 200),
        "cls_threshold": _safe_float(rows.get("faro.web_vitals_threshold_cls"), 0.1),
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
    """Strip volatile content so similar error lines share a fingerprint.

    Reuses the loki picker's ``_NORMALIZE_PATTERNS`` (timestamps, UUIDs,
    hex addresses, line numbers, long ints) — Faro events look very
    similar to backend log lines once stringified.
    """
    out = line
    for pattern, replacement in _NORMALIZE_PATTERNS:
        out = pattern.sub(replacement, out)
    out = re.sub(r"\s+", " ", out).strip()
    return out[:512]


def _stable_fingerprint(prefix: str, payload: str) -> str:
    return f"{prefix}::{hashlib.sha1(payload.encode()).hexdigest()[:16]}"


def _fetch_faro_lines(
    api_url: str, *, query: str, window_s: int, limit: int
) -> list[str]:
    """Pull raw Faro log lines from Loki. Returns the line bodies."""
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
        logger.warning("[faro_picker] query_range failed: %s", exc)
        return []
    streams = (body.get("data") or {}).get("result") or []
    out: list[str] = []
    for stream in streams:
        for _ts_ns, line in stream.get("values") or []:
            out.append(line)
    return out


# logfmt field extractor — Alloy's faro.receiver emits each Faro event
# as a line of `key="value" key=value ...` pairs (not JSON). The fields
# we care about are quoted, so a single regex pulls them out cleanly.
_LOGFMT_FIELD_RE = re.compile(r'\b(?P<key>\w+)="(?P<val>(?:[^"\\]|\\.)*)"')


def _parse_faro_event(raw: str) -> dict[str, Any]:
    """Best-effort parse of one Faro event line.

    Tries JSON first (some Faro pipelines emit JSON directly); falls
    back to logfmt — which is what Alloy's faro.receiver actually emits
    when forwarding to Loki via ``loki.write``. Returns an empty dict
    on total failure so the picker can fall back to using the raw line.

    Faro error events contain ``message`` and ``level``; exception
    events contain ``type`` + ``value``; measurement events contain
    ``name`` (LCP/INP/CLS), ``value``, ``url``.
    """
    raw = raw.strip()
    if raw.startswith("{"):
        try:
            return json.loads(raw)
        except (json.JSONDecodeError, ValueError):
            pass
    # logfmt path — extract every `key="value"` pair.
    out: dict[str, Any] = {}
    for m in _LOGFMT_FIELD_RE.finditer(raw):
        out[m.group("key")] = m.group("val")
    # Faro exceptions ship `value="..."` and `kind=exception`; logs
    # ship `message="..."` and `kind=log`. Normalize so callers can
    # always read `message`. The `type=measurement` route uses `name`
    # so we leave that field as-is.
    if "message" not in out and "value" in out:
        out["message"] = out["value"]
    if "kind" in out and "type" not in out:
        out["type"] = out["kind"]
    # `value` is numeric for measurement events; logfmt parser
    # captured it as a string. Coerce to float when the key is a
    # measurement-style field.
    if out.get("type") == "measurement" and "value" in out:
        try:
            out["value"] = float(out["value"])
        except (TypeError, ValueError):
            pass
    return out


# --- Error clusters --------------------------------------------------


def _gather_error_clusters(
    api_url: str, *, window_s: int, min_count: int, max_lines: int
) -> list[FaroCandidate]:
    query = f"{_FARO_LABEL} {_ERROR_FILTER}"
    rows = _fetch_faro_lines(
        api_url, query=query, window_s=window_s, limit=max_lines
    )
    if not rows:
        return []

    grouped: dict[str, dict[str, Any]] = {}
    for line in rows:
        parsed = _parse_faro_event(line)
        message = parsed.get("message") or line
        route = parsed.get("url") or parsed.get("route") or "unknown"
        normalized = _normalize_line(str(message))
        if not normalized:
            continue
        bucket = grouped.setdefault(
            normalized,
            {"count": 0, "sample": message, "route": route},
        )
        bucket["count"] += 1

    out: list[FaroCandidate] = []
    for normalized, data in grouped.items():
        if data["count"] < min_count:
            continue
        out.append(
            FaroCandidate(
                kind="error_cluster",
                fingerprint=_stable_fingerprint("faro:err", normalized),
                sample_message=str(data["sample"])[:512],
                route_or_metric=str(data["route"])[:200],
                occurrence_count=int(data["count"]),
                extra=(
                    f"JS error occurred {data['count']}x in the last "
                    f"{window_s // 3600} h. Sample route: {data['route']}."
                ),
            )
        )
    return out


# --- Web Vitals breaches ---------------------------------------------


def _accumulate_breach(
    grouped: dict[tuple[str, str], dict[str, Any]],
    line: str,
    thresholds: dict[str, float],
) -> None:
    """If `line` is a measurement event over its metric threshold, bump
    the matching (metric, route) bucket in `grouped`. No-op otherwise.
    Extracted from `_gather_webvital_breaches` to keep that function
    under the 50-line cap.
    """
    evt = _parse_faro_event(line)
    if evt.get("type") != "measurement":
        return
    metric = str(evt.get("name") or "").strip()
    threshold = thresholds.get(metric)
    if threshold is None:
        return
    try:
        value = float(evt.get("value", 0))
    except (TypeError, ValueError):
        return
    if value <= threshold:
        return
    route = str(evt.get("url") or evt.get("route") or "unknown")[:200]
    bucket = grouped.setdefault(
        (metric, route),
        {"count": 0, "max_value": 0.0, "threshold": threshold},
    )
    bucket["count"] += 1
    if value > bucket["max_value"]:
        bucket["max_value"] = value


def _gather_webvital_breaches(
    api_url: str, *, window_s: int, max_lines: int,
    lcp_ms: int, inp_ms: int, cls: float,
) -> list[FaroCandidate]:
    query = f'{_FARO_LABEL} |~ "measurement"'
    rows = _fetch_faro_lines(
        api_url, query=query, window_s=window_s, limit=max_lines
    )
    if not rows:
        return []

    thresholds = {
        "largest_contentful_paint": float(lcp_ms),
        "interaction_to_next_paint": float(inp_ms),
        "cumulative_layout_shift": float(cls),
    }
    # Group by (metric_name, route) so a slow route accumulates samples.
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for line in rows:
        _accumulate_breach(grouped, line, thresholds)

    out: list[FaroCandidate] = []
    for (metric, route), data in grouped.items():
        if data["count"] < _WEBVITAL_MIN_SAMPLES:
            continue
        unit = "" if metric == "cumulative_layout_shift" else " ms"
        out.append(
            FaroCandidate(
                kind="webvital_breach",
                fingerprint=_stable_fingerprint(
                    f"faro:webvital::{metric}", route
                ),
                sample_message=(
                    f"Web Vital breach: {metric} peaked at "
                    f"{data['max_value']:.2f}{unit} on {route}"
                ),
                route_or_metric=metric,
                occurrence_count=int(data["count"]),
                extra=(
                    f"{data['count']} sessions over the "
                    f"{data['threshold']:.2f}{unit} threshold in the last "
                    f"{window_s // 3600} h. Worst sample: "
                    f"{data['max_value']:.2f}{unit}."
                ),
            )
        )
    return out


# --- Common upsert + scoring -----------------------------------------


def _candidate_for_score(fc: FaroCandidate, max_blast: float) -> Candidate:
    severity = (
        AutoIssue.SEVERITY_HIGH
        if fc.occurrence_count > 50
        else AutoIssue.SEVERITY_MEDIUM
    )
    return Candidate(
        source=AutoIssue.SOURCE_FARO,
        external_id=fc.fingerprint,
        fingerprint=fc.fingerprint,
        severity=severity,
        last_seen=timezone.now(),
        blast_observed=float(fc.occurrence_count),
        blast_max=float(max(max_blast, 1)),
        num_affected_files=0,
    )


def _upsert_faro_row(score: float, fc: FaroCandidate) -> str:
    title = f"Faro: [{fc.kind}] {fc.sample_message[:160]}"
    description = (
        f"{fc.extra}\n\n"
        f"Route / metric: `{fc.route_or_metric}`\n"
        f"Sample: ```{fc.sample_message[:480]}```"
    )
    canonical = canonical_fingerprint(
        fc.sample_message[:200], fc.route_or_metric
    )
    severity = (
        AutoIssue.SEVERITY_HIGH
        if fc.occurrence_count > 50
        else AutoIssue.SEVERITY_MEDIUM
    )
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_FARO,
        external_id=fc.fingerprint,
        fingerprint=fc.fingerprint,
        title=title[:512],
        description=description[:4000],
        affected_files=[],
        severity=severity,
        priority_score=float(score),
        occurrence_count=fc.occurrence_count,
    )
    return outcome


def _score_and_promote(cands: list[FaroCandidate], *, limit: int) -> int:
    if not cands:
        return 0
    max_blast = max(c.occurrence_count for c in cands)
    scored = [
        (score_candidate(_candidate_for_score(c, max_blast)), c)
        for c in cands
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    promoted = 0
    for score, c in scored[:limit]:
        _upsert_faro_row(score, c)
        promoted += 1
    return promoted


# --- Public API ------------------------------------------------------


def pick_faro_error_clusters(*, limit: int = _MAX_PER_RUN) -> dict:
    """Surface recurring JS errors from Faro as AutoIssues."""
    settings = _read_faro_settings()
    cands = _gather_error_clusters(
        settings["loki_api_url"],
        window_s=settings["scan_window_seconds"],
        min_count=settings["error_min_count"],
        max_lines=settings["max_lines_per_query"],
    )
    promoted = _score_and_promote(cands, limit=limit)
    logger.info(
        "[faro_picker.error_clusters] candidates=%d promoted=%d "
        "min_count=%d window_s=%d",
        len(cands), promoted,
        settings["error_min_count"], settings["scan_window_seconds"],
    )
    return {
        "status": "ok",
        "clusters_found": len(cands),
        "promoted": promoted,
    }


def pick_faro_webvital_breaches(*, limit: int = _MAX_PER_RUN) -> dict:
    """Surface Web Vitals breaches (LCP / INP / CLS) from Faro as AutoIssues."""
    settings = _read_faro_settings()
    cands = _gather_webvital_breaches(
        settings["loki_api_url"],
        window_s=settings["scan_window_seconds"],
        max_lines=settings["max_lines_per_query"],
        lcp_ms=settings["lcp_threshold_ms"],
        inp_ms=settings["inp_threshold_ms"],
        cls=settings["cls_threshold"],
    )
    promoted = _score_and_promote(cands, limit=limit)
    logger.info(
        "[faro_picker.webvital_breaches] candidates=%d promoted=%d "
        "lcp_ms=%d inp_ms=%d cls=%.2f",
        len(cands), promoted,
        settings["lcp_threshold_ms"], settings["inp_threshold_ms"],
        settings["cls_threshold"],
    )
    return {
        "status": "ok",
        "breaches_found": len(cands),
        "promoted": promoted,
    }


def pick_faro_findings(*, limit: int = _MAX_PER_RUN) -> dict:
    """Convenience wrapper — runs both detectors in one call."""
    errors = pick_faro_error_clusters(limit=limit)
    webvitals = pick_faro_webvital_breaches(limit=limit)
    return {"error_clusters": errors, "webvital_breaches": webvitals}
