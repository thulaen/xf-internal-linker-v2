"""Tempo -> AutoIssue picker.

Tempo is Grafana's distributed-trace backend. The otel-collector fans
spans out to BOTH the Sentry exporter (-> GlitchTip, ABSOLUTE-protected)
AND a new ``otlp/tempo`` exporter, so the same trace lives in both
stores and we can correlate a GlitchTip error event to its full Tempo
trace via the shared traceID.

This picker queries Tempo's TraceQL ``/api/search`` HTTP endpoint and
promotes recurring problems as ``AutoIssue(source='tempo')`` rows.

Two detectors with disjoint fingerprint prefixes so they never collide
on the ``(source, external_id)`` unique constraint:

  - ``pick_tempo_slow_spans`` — spans whose duration exceeds
    ``tempo.slow_span_threshold_ms``, grouped by
    ``(span_name, service.name)``.
  - ``pick_tempo_error_spans`` — spans with ``status=error``, grouped
    by the same key, promoted when count ≥
    ``tempo.error_span_min_count``.

Both feed through the existing ``upsert_dedup`` plumbing so a slow span
also surfaced as a GlitchTip Performance transaction collapses into one
canonical row via ``source_observations``.

Added 2026-05-11 per plan
``~/.claude/plans/objective-deploy-and-integrate-zany-bee.md`` Stream 6.
"""

from __future__ import annotations

import hashlib
import logging
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


@dataclass(frozen=True)
class TempoCandidate:
    """One promotable Tempo finding (slow span OR error span)."""

    kind: str  # "slow_span" | "error_span"
    fingerprint: str
    span_name: str
    service_name: str
    occurrence_count: int
    max_duration_ms: float  # 0.0 for error_span; peak duration for slow_span
    extra: str  # human-readable description detail


# --- Helpers ---------------------------------------------------------


def _read_tempo_settings() -> dict[str, Any]:
    """Read tunable thresholds from AppSetting with safe fallbacks."""
    from apps.core.models import AppSetting

    keys = (
        "tempo.query_url",
        "tempo.slow_span_threshold_ms",
        "tempo.error_span_min_count",
        "tempo.scan_window_seconds",
    )
    rows = {
        s.key: s.value
        for s in AppSetting.objects.filter(key__in=keys).only("key", "value")
    }
    return {
        "query_url": rows.get("tempo.query_url", "http://tempo:3200"),
        "slow_span_threshold_ms": _safe_int(
            rows.get("tempo.slow_span_threshold_ms"), 1000
        ),
        "error_span_min_count": _safe_int(
            rows.get("tempo.error_span_min_count"), 3
        ),
        "scan_window_seconds": _safe_int(
            rows.get("tempo.scan_window_seconds"), 3600
        ),
    }


def _safe_int(raw, fallback: int) -> int:
    try:
        return int(raw) if raw is not None else fallback
    except (TypeError, ValueError):
        return fallback


def _stable_fingerprint(prefix: str, payload: str) -> str:
    return f"{prefix}::{hashlib.sha1(payload.encode()).hexdigest()[:16]}"


def _tempo_search(
    query_url: str, *, traceql: str, window_s: int, limit: int = 200
) -> list[dict[str, Any]]:
    """Run a TraceQL ``/api/search`` query. Returns the raw trace list.

    No-ops cleanly (returns []) on any HTTP failure so a Tempo outage
    never crashes the picker beat task.
    """
    end_s = int(timezone.now().timestamp())
    start_s = end_s - window_s
    params = {
        "q": traceql,
        "start": start_s,
        "end": end_s,
        "limit": limit,
    }
    try:
        r = requests.get(
            f"{query_url.rstrip('/')}/api/search",
            params=params,
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        body = r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[tempo_picker] search failed: %s", exc)
        return []
    return list(body.get("traces") or [])


def _iter_root_spans(traces: list[dict[str, Any]]):
    """Yield ``(span_name, service_name, duration_ms, has_error)`` per trace.

    Tempo's ``/api/search`` returns one entry per trace with
    ``rootServiceName``, ``rootTraceName``, ``durationMs``, and a
    ``spanSets`` array of matching spans. The picker treats one matched
    span per trace as one candidate observation.
    """
    for t in traces:
        service = str(t.get("rootServiceName") or "unknown")
        name = str(t.get("rootTraceName") or "unknown")
        # durationMs may be string or number depending on Tempo build.
        raw_dur = t.get("durationMs") or t.get("duration") or 0
        try:
            duration_ms = float(raw_dur)
        except (TypeError, ValueError):
            duration_ms = 0.0
        # Errors surface either as status=error attribute OR as the trace
        # itself being tagged error. Be generous: any matching trace is
        # considered an error when this iterator is called with the
        # error TraceQL.
        yield name, service, duration_ms, True


# --- Slow spans ------------------------------------------------------


def _gather_slow_spans(
    query_url: str, *, threshold_ms: int, window_s: int
) -> list[TempoCandidate]:
    """Find spans whose duration exceeds the threshold; group by (name, svc)."""
    traceql = f"{{ duration > {threshold_ms}ms }}"
    traces = _tempo_search(query_url, traceql=traceql, window_s=window_s)
    if not traces:
        return []

    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for name, service, duration_ms, _is_error in _iter_root_spans(traces):
        key = (name, service)
        bucket = grouped.setdefault(
            key, {"count": 0, "max_duration_ms": 0.0}
        )
        bucket["count"] += 1
        if duration_ms > bucket["max_duration_ms"]:
            bucket["max_duration_ms"] = duration_ms

    out: list[TempoCandidate] = []
    for (name, service), data in grouped.items():
        out.append(
            TempoCandidate(
                kind="slow_span",
                fingerprint=_stable_fingerprint(
                    "tempo:slow", f"{service}::{name}"
                ),
                span_name=name,
                service_name=service,
                occurrence_count=int(data["count"]),
                max_duration_ms=float(data["max_duration_ms"]),
                extra=(
                    f"Span `{name}` in service `{service}` exceeded "
                    f"{threshold_ms} ms on {data['count']} trace(s) in "
                    f"the last {window_s // 60} min. Peak duration: "
                    f"{data['max_duration_ms']:.0f} ms."
                ),
            )
        )
    return out


# --- Error spans -----------------------------------------------------


def _gather_error_spans(
    query_url: str, *, min_count: int, window_s: int
) -> list[TempoCandidate]:
    traceql = "{ status = error }"
    traces = _tempo_search(query_url, traceql=traceql, window_s=window_s)
    if not traces:
        return []

    grouped: dict[tuple[str, str], int] = {}
    for name, service, _duration_ms, _is_error in _iter_root_spans(traces):
        key = (name, service)
        grouped[key] = grouped.get(key, 0) + 1

    out: list[TempoCandidate] = []
    for (name, service), count in grouped.items():
        if count < min_count:
            continue
        out.append(
            TempoCandidate(
                kind="error_span",
                fingerprint=_stable_fingerprint(
                    "tempo:err", f"{service}::{name}"
                ),
                span_name=name,
                service_name=service,
                occurrence_count=count,
                max_duration_ms=0.0,
                extra=(
                    f"Span `{name}` in service `{service}` had status=error "
                    f"on {count} trace(s) in the last "
                    f"{window_s // 60} min."
                ),
            )
        )
    return out


# --- Common upsert + scoring -----------------------------------------


def _candidate_for_score(tc: TempoCandidate, max_blast: float) -> Candidate:
    if tc.kind == "error_span":
        severity = (
            AutoIssue.SEVERITY_HIGH if tc.occurrence_count > 10
            else AutoIssue.SEVERITY_MEDIUM
        )
    else:
        severity = (
            AutoIssue.SEVERITY_HIGH if tc.max_duration_ms > 5000
            else AutoIssue.SEVERITY_MEDIUM
        )
    return Candidate(
        source=AutoIssue.SOURCE_TEMPO,
        external_id=tc.fingerprint,
        fingerprint=tc.fingerprint,
        severity=severity,
        last_seen=timezone.now(),
        blast_observed=float(tc.occurrence_count),
        blast_max=float(max(max_blast, 1)),
        num_affected_files=0,
    )


def _upsert_tempo_row(score: float, tc: TempoCandidate) -> str:
    title = (
        f"Tempo: [{tc.kind}] {tc.span_name} (service={tc.service_name})"
        + (
            f" — peak {tc.max_duration_ms:.0f} ms"
            if tc.kind == "slow_span"
            else f" — {tc.occurrence_count} errors"
        )
    )
    description = (
        f"{tc.extra}\n\n"
        f"Span name: `{tc.span_name}`\n"
        f"Service: `{tc.service_name}`\n"
        f"Occurrences: {tc.occurrence_count}"
    )
    canonical = canonical_fingerprint(tc.span_name, tc.service_name)
    severity_for_row = (
        AutoIssue.SEVERITY_HIGH
        if (tc.kind == "error_span" and tc.occurrence_count > 10)
        or (tc.kind == "slow_span" and tc.max_duration_ms > 5000)
        else AutoIssue.SEVERITY_MEDIUM
    )
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_TEMPO,
        external_id=tc.fingerprint,
        fingerprint=tc.fingerprint,
        title=title[:512],
        description=description[:4000],
        affected_files=[],
        severity=severity_for_row,
        priority_score=float(score),
        occurrence_count=tc.occurrence_count,
    )
    return outcome


def _score_and_promote(cands: list[TempoCandidate], *, limit: int) -> int:
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
        _upsert_tempo_row(score, c)
        promoted += 1
    return promoted


# --- Public API ------------------------------------------------------


def pick_tempo_slow_spans(*, limit: int = _MAX_PER_RUN) -> dict:
    """Surface slow span clusters from Tempo as AutoIssues."""
    settings = _read_tempo_settings()
    cands = _gather_slow_spans(
        settings["query_url"],
        threshold_ms=settings["slow_span_threshold_ms"],
        window_s=settings["scan_window_seconds"],
    )
    promoted = _score_and_promote(cands, limit=limit)
    logger.info(
        "[tempo_picker.slow_spans] candidates=%d promoted=%d "
        "threshold_ms=%d window_s=%d",
        len(cands), promoted,
        settings["slow_span_threshold_ms"], settings["scan_window_seconds"],
    )
    return {
        "status": "ok",
        "slow_spans_found": len(cands),
        "promoted": promoted,
    }


def pick_tempo_error_spans(*, limit: int = _MAX_PER_RUN) -> dict:
    """Surface error span clusters from Tempo as AutoIssues."""
    settings = _read_tempo_settings()
    cands = _gather_error_spans(
        settings["query_url"],
        min_count=settings["error_span_min_count"],
        window_s=settings["scan_window_seconds"],
    )
    promoted = _score_and_promote(cands, limit=limit)
    logger.info(
        "[tempo_picker.error_spans] candidates=%d promoted=%d "
        "min_count=%d window_s=%d",
        len(cands), promoted,
        settings["error_span_min_count"], settings["scan_window_seconds"],
    )
    return {
        "status": "ok",
        "error_spans_found": len(cands),
        "promoted": promoted,
    }


def pick_tempo_findings(*, limit: int = _MAX_PER_RUN) -> dict:
    """Convenience wrapper — runs both detectors in one call."""
    slow = pick_tempo_slow_spans(limit=limit)
    errors = pick_tempo_error_spans(limit=limit)
    return {"slow_spans": slow, "error_spans": errors}
