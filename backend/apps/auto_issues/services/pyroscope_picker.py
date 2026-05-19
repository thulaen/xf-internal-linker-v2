"""Pyroscope → AutoIssue picker — regression + hotspot detection.

Two complementary detectors:

1. ``pick_pyroscope_regressions`` — week-over-week. Surfaces functions
   whose self-CPU grew ≥2× week-over-week AND account for ≥5 % of the
   total runtime. Needs 7 days of profile history.

2. ``pick_pyroscope_hotspots`` — same-day. Surfaces any function whose
   self-CPU exceeds X % of total runtime in the last hour. No history
   required, so it produces findings from day one (added 2026-05-10
   per plan ``does-adding-qodana-make-swift-wall.md`` Stream 2).

Both write AutoIssue rows with ``source='pyroscope'`` and a priority
score from ``services.scoring``. Regression and hotspot rows use separate
fingerprint prefixes so they do not collide in the AutoIssue table.

Design decisions (from SPEC § Open design decisions):
  - (d) We query 24h chunks instead of 7-day windows so a single API
    call can never exceed a few MB. Two queries: today + same-day-last-week.
  - We do NOT auto-assign (decision (c)); rows land as `status='open'`.

Pyroscope HTTP API used (OSS 1.9 — Phlare-derived):
  GET /pyroscope/render-diff?from=...&until=...&query=...    (regressions)
  GET /pyroscope/render?from=...&until=...&query=...         (hotspots)
The diff endpoint returns left/right flamegraphs for week-over-week
comparison. The render endpoint returns a single flamegraph for the
last-hour hotspot view.
"""

from __future__ import annotations

import hashlib
import logging
import os
import time
from dataclasses import dataclass
from typing import Any

import requests
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.scoring import Candidate, score_candidate

logger = logging.getLogger(__name__)

# Defaults from the SPEC § Pyroscope issue criteria.
_REGRESSION_RATIO_THRESHOLD = 2.0  # right is at least 2x left
_MIN_SHARE_OF_TOTAL = 0.05  # function must be ≥5 % of total runtime
_MIN_LEFT_TOTAL_NS = 1_000_000  # ignore functions that barely existed last week (1 ms)
_REQUEST_TIMEOUT = 15.0
_MAX_PER_RUN = 10


@dataclass(frozen=True)
class PyroscopeCandidate:
    """Internal — one regressed function, raw measurements."""

    function_name: str
    file_hint: str
    left_self_ns: float
    right_self_ns: float
    right_total_ns: float


def _stable_fingerprint(function_name: str, file_hint: str) -> str:
    raw = f"pyroscope::{function_name}::{file_hint}"
    return hashlib.sha1(raw.encode(), usedforsecurity=False).hexdigest()[:16]


def _pyroscope_cpu_query(application: str) -> str:
    return (
        "process_cpu:cpu:nanoseconds:cpu:nanoseconds"
        f"{{service_name=\"{application}\"}}"
    )


def _query_pyroscope_diff(
    server: str,
    application: str,
    *,
    until: int,
    span_seconds: int = 86400,
) -> dict[str, Any]:
    """Fetch a single diff response from Pyroscope.

    `until` is a unix timestamp; the diff compares
    (`until - 7d - span` .. `until - 7d`) vs (`until - span` .. `until`).
    Returns the raw JSON. On any HTTP failure returns an empty dict so
    the caller can no-op cleanly.
    """
    week_seconds = 7 * 86400
    params = {
        "from": (until - span_seconds) * 1000,
        "until": until * 1000,
        "leftFrom": (until - span_seconds - week_seconds) * 1000,
        "leftUntil": (until - week_seconds) * 1000,
        "leftQuery": _pyroscope_cpu_query(application),
        "rightQuery": _pyroscope_cpu_query(application),
        "format": "json",
    }
    try:
        r = requests.get(
            f"{server.rstrip('/')}/pyroscope/render-diff",
            params=params,
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[pyroscope_picker] diff fetch failed: %s", exc)
        return {}


def _extract_function_totals(side: dict[str, Any]) -> dict[str, float]:
    """Walk a Pyroscope flamegraph response and sum self-time per function.

    Schema varies across Pyroscope versions; this implementation handles
    the common shape `{"flamebearer": {"names": [...], "levels": [[...]]}}`
    used by Pyroscope OSS 1.9. Each level is a flat list of
    `[offset_left, total, self, name_index, ...]` quadruples per node.
    """
    flamebearer = side.get("flamebearer") or {}
    names = flamebearer.get("names") or []
    levels = flamebearer.get("levels") or []
    totals: dict[str, float] = {}
    for level in levels:
        for i in range(0, len(level), 4):
            try:
                self_val = float(level[i + 2])
                name_idx = int(level[i + 3])
            except (IndexError, ValueError, TypeError):
                continue
            if 0 <= name_idx < len(names):
                fn_name = names[name_idx] or ""
                totals[fn_name] = totals.get(fn_name, 0.0) + self_val
    return totals


def _compare_sides(
    left_totals: dict[str, float],
    right_totals: dict[str, float],
) -> list[PyroscopeCandidate]:
    """Return functions whose right >= 2x left AND >= 5% of right total."""
    right_grand_total = sum(right_totals.values()) or 1.0
    candidates: list[PyroscopeCandidate] = []
    for fn_name, right_self in right_totals.items():
        if right_self / right_grand_total < _MIN_SHARE_OF_TOTAL:
            continue
        left_self = left_totals.get(fn_name, 0.0)
        # Skip functions that barely existed last week (avoids
        # 'new function = infinite ratio' noise).
        if left_self < _MIN_LEFT_TOTAL_NS:
            continue
        ratio = right_self / left_self
        if ratio < _REGRESSION_RATIO_THRESHOLD:
            continue
        # Best-effort file hint — Pyroscope sometimes encodes file in
        # the function name as `module/file.py:lineno`. Fall back to "".
        file_hint = ""
        if ":" in fn_name and "/" in fn_name:
            file_hint = fn_name.split(":", 1)[0]
        candidates.append(
            PyroscopeCandidate(
                function_name=fn_name,
                file_hint=file_hint,
                left_self_ns=left_self,
                right_self_ns=right_self,
                right_total_ns=right_grand_total,
            )
        )
    return candidates


def _severity_for(pc: PyroscopeCandidate) -> str:
    """Map regression magnitude → severity string per SPEC table."""
    ratio = pc.right_self_ns / max(pc.left_self_ns, 1.0)
    if ratio >= 5.0:
        return AutoIssue.SEVERITY_HIGH
    if ratio >= 2.0:
        return AutoIssue.SEVERITY_MEDIUM
    return AutoIssue.SEVERITY_LOW


def _candidate_for_score(pc: PyroscopeCandidate, max_blast: float) -> Candidate:
    return Candidate(
        source=AutoIssue.SOURCE_PYROSCOPE,
        external_id=_stable_fingerprint(pc.function_name, pc.file_hint),
        fingerprint=_stable_fingerprint(pc.function_name, pc.file_hint),
        severity=_severity_for(pc),
        last_seen=timezone.now(),
        blast_observed=pc.right_self_ns,
        blast_max=max_blast,
        num_affected_files=1 if pc.file_hint else 0,
    )


def _gather_regressions(
    server: str, applications: tuple[str, ...]
) -> list[PyroscopeCandidate]:
    """Query each application, parse diffs, accumulate regression candidates."""
    until = int(time.time())
    cands: list[PyroscopeCandidate] = []
    for app in applications:
        diff = _query_pyroscope_diff(server, app, until=until)
        if not diff:
            continue
        left = _extract_function_totals(diff.get("left") or {})
        right = _extract_function_totals(diff.get("right") or {})
        cands.extend(_compare_sides(left, right))
    return cands


def _score_regressions(
    cands: list[PyroscopeCandidate],
) -> list[tuple[float, PyroscopeCandidate]]:
    """Score each candidate; sort descending."""
    if not cands:
        return []
    max_blast = max(c.right_self_ns for c in cands)
    scored = [(score_candidate(_candidate_for_score(pc, max_blast)), pc) for pc in cands]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return scored


def _upsert_pyroscope_row(
    score: float, pc: PyroscopeCandidate, now
) -> str:
    """Cross-source-dedup upsert for one Pyroscope regression. Returns outcome."""
    ratio = pc.right_self_ns / max(pc.left_self_ns, 1.0)
    title = f"Pyroscope: {pc.function_name[:200]} CPU regressed {ratio:.1f}x WoW"
    description = (
        f"Function `{pc.function_name}` self-CPU rose from "
        f"{pc.left_self_ns / 1e6:.1f}ms (last week) to "
        f"{pc.right_self_ns / 1e6:.1f}ms (this week). "
        f"Accounts for {pc.right_self_ns * 100 / pc.right_total_ns:.1f}% "
        f"of total runtime. Ratio = {ratio:.2f}x."
    )
    canonical = canonical_fingerprint(pc.function_name, pc.file_hint)
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_PYROSCOPE,
        external_id=_stable_fingerprint(pc.function_name, pc.file_hint),
        fingerprint=_stable_fingerprint(pc.function_name, pc.file_hint),
        title=title,
        description=description,
        affected_files=[pc.file_hint] if pc.file_hint else [],
        severity=_severity_for(pc),
        priority_score=float(score),
        occurrence_count=int(pc.right_self_ns / 1e6),
    )
    return outcome


def pick_pyroscope_regressions(
    *,
    server: str | None = None,
    applications: tuple[str, ...] = (
        "xf-linker-backend",
        "xf-linker-celery-default",
        "xf-linker-celery-pipeline",
        "xf-linker-celery-beat",
    ),
    limit: int = _MAX_PER_RUN,
) -> dict:
    """Top-level entrypoint — fetch, compare, score, upsert.

    Returns a small dict with counts. No-ops cleanly when the Pyroscope
    server is unreachable or returns no flamegraph data.
    """
    server = server or os.environ.get("PYROSCOPE_SERVER_ADDRESS", "")
    if not server:
        return {"status": "skipped", "reason": "missing_pyroscope_server"}

    cands = _gather_regressions(server, applications)
    if not cands:
        return {"status": "ok", "regressions_found": 0, "promoted": 0}

    scored = _score_regressions(cands)
    now = timezone.now()
    for score, pc in scored[:limit]:
        _upsert_pyroscope_row(score, pc, now)

    logger.info(
        "[auto_issues.pyroscope_picker] regressions=%d promoted=%d",
        len(cands),
        min(len(scored), limit),
    )
    return {
        "status": "ok",
        "regressions_found": len(cands),
        "promoted": min(len(scored), limit),
    }


# --- Same-day hotspot detector ---------------------------------------------
#
# Added 2026-05-10 per plan ``does-adding-qodana-make-swift-wall.md``
# Stream 2. The week-over-week regressions detector above needs 7 days of
# profile history; this detector works from day one.

_HOTSPOT_PCT_DEFAULT = 5.0
_HOTSPOT_WINDOW_DEFAULT_S = 3600
_PROFILER_TOOLING_EXACT_NAMES = frozenset({"Runner.run", "sleep"})
_PROFILER_TOOLING_FRAGMENTS = (
    "Scheduler.make_sampler.<locals>._sample_stack",
    "encode_metrics",
)


def _read_hotspot_settings() -> tuple[float, int]:
    """Read tunable hotspot thresholds from AppSetting with constant fallback.

    Returns ``(threshold_pct, window_seconds)``. Defaults match the
    seed values in migration ``0004_seed_pyroscope_hotspot_threshold``.
    Falls back to module constants if AppSetting rows are missing
    (fresh test DB, etc.).
    """
    from apps.core.models import AppSetting

    pct_row = AppSetting.objects.filter(
        key="pyroscope.hotspot_pct_threshold"
    ).only("value").first()
    win_row = AppSetting.objects.filter(
        key="pyroscope.hotspot_window_seconds"
    ).only("value").first()
    try:
        pct = float(pct_row.value) if pct_row else _HOTSPOT_PCT_DEFAULT
    except (TypeError, ValueError):
        pct = _HOTSPOT_PCT_DEFAULT
    try:
        win = int(win_row.value) if win_row else _HOTSPOT_WINDOW_DEFAULT_S
    except (TypeError, ValueError):
        win = _HOTSPOT_WINDOW_DEFAULT_S
    return pct, win


def _query_pyroscope_render(
    server: str,
    application: str,
    *,
    until: int,
    span_seconds: int,
) -> dict[str, Any]:
    """Fetch a single-period flamegraph from Pyroscope (no diff).

    Returns the raw JSON. On any HTTP failure returns an empty dict so
    the caller can no-op cleanly. Pyroscope OSS 1.x render endpoint
    returns a top-level ``flamebearer`` payload — same shape that
    ``_extract_function_totals`` already understands.
    """
    params = {
        "from": (until - span_seconds) * 1000,
        "until": until * 1000,
        "query": _pyroscope_cpu_query(application),
        "format": "json",
    }
    try:
        r = requests.get(
            f"{server.rstrip('/')}/pyroscope/render",
            params=params,
            timeout=_REQUEST_TIMEOUT,
        )
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("[pyroscope_picker] render fetch failed: %s", exc)
        return {}


def _select_hotspots(
    totals: dict[str, float], threshold_pct: float
) -> list[PyroscopeCandidate]:
    """Return functions whose self-time ≥ threshold_pct of grand total."""
    grand_total = sum(totals.values()) or 1.0
    threshold_share = max(threshold_pct, 0.0) / 100.0
    candidates: list[PyroscopeCandidate] = []
    for fn_name, self_ns in totals.items():
        if self_ns / grand_total < threshold_share:
            continue
        file_hint = ""
        if ":" in fn_name and "/" in fn_name:
            file_hint = fn_name.split(":", 1)[0]
        candidates.append(
            PyroscopeCandidate(
                function_name=fn_name,
                file_hint=file_hint,
                left_self_ns=0.0,  # no historical comparison
                right_self_ns=self_ns,
                right_total_ns=grand_total,
            )
        )
    return candidates


def _is_profiler_tooling_hotspot(pc: PyroscopeCandidate) -> bool:
    name = pc.function_name
    if name in _PROFILER_TOOLING_EXACT_NAMES:
        return True
    return any(fragment in name for fragment in _PROFILER_TOOLING_FRAGMENTS)


def _split_profiler_tooling_hotspots(
    cands: list[PyroscopeCandidate],
) -> tuple[list[PyroscopeCandidate], list[PyroscopeCandidate]]:
    app_cands: list[PyroscopeCandidate] = []
    tooling_cands: list[PyroscopeCandidate] = []
    for pc in cands:
        if _is_profiler_tooling_hotspot(pc):
            tooling_cands.append(pc)
        else:
            app_cands.append(pc)
    return app_cands, tooling_cands


def _gather_hotspots(
    server: str,
    applications: tuple[str, ...],
    *,
    threshold_pct: float,
    window_s: int,
) -> list[PyroscopeCandidate]:
    until = int(time.time())
    cands: list[PyroscopeCandidate] = []
    for app in applications:
        payload = _query_pyroscope_render(
            server, app, until=until, span_seconds=window_s
        )
        if not payload:
            continue
        totals = _extract_function_totals(payload)
        cands.extend(_select_hotspots(totals, threshold_pct))
    return cands


def _upsert_hotspot_row(score: float, pc: PyroscopeCandidate) -> str:
    """Cross-source-dedup upsert for one same-day hotspot. Returns outcome."""
    share_pct = pc.right_self_ns * 100.0 / max(pc.right_total_ns, 1.0)
    title = (
        f"Pyroscope: {pc.function_name[:200]} burning "
        f"{share_pct:.1f}% of CPU"
    )
    description = (
        f"Function `{pc.function_name}` accounts for {share_pct:.1f}% "
        f"of total CPU in the last hour ({pc.right_self_ns / 1e6:.1f} ms "
        f"self-time). No week-over-week history required — this is a "
        "same-day hotspot. Investigate whether the workload is expected "
        "or this is an opportunity for a C++ extension / caching."
    )
    canonical = canonical_fingerprint(pc.function_name, pc.file_hint)
    fingerprint = _stable_fingerprint(
        f"hotspot::{pc.function_name}", pc.file_hint
    )
    _, outcome = upsert_dedup(
        canonical=canonical,
        source=AutoIssue.SOURCE_PYROSCOPE,
        external_id=fingerprint,
        fingerprint=fingerprint,
        title=title,
        description=description,
        affected_files=[pc.file_hint] if pc.file_hint else [],
        severity=AutoIssue.SEVERITY_MEDIUM,
        priority_score=float(score),
        occurrence_count=int(pc.right_self_ns / 1e6),
    )
    return outcome


def _format_tooling_hotspot(pc: PyroscopeCandidate) -> str:
    share_pct = pc.right_self_ns * 100.0 / max(pc.right_total_ns, 1.0)
    return f"{pc.function_name} ({share_pct:.1f}%)"


def _upsert_profiler_tooling_row(cands: list[PyroscopeCandidate]) -> str:
    max_blast = max(c.right_self_ns for c in cands)
    score = max(
        score_candidate(_candidate_for_score(pc, max_blast)) for pc in cands
    )
    total_self_ns = sum(c.right_self_ns for c in cands)
    observed = ", ".join(_format_tooling_hotspot(pc) for pc in cands[:6])
    fingerprint = _stable_fingerprint(
        "hotspot::profiler-tooling-overhead", "pyroscope"
    )
    title = "Pyroscope: profiler-tooling overhead is above threshold"
    description = (
        "Pyroscope reported profiler or framework overhead above the hotspot "
        f"threshold: {observed}. The picker grouped these functions into one "
        "tooling issue so sampler, sleep, and metrics overhead do not create "
        "separate app-performance issues."
    )
    _, outcome = upsert_dedup(
        canonical=canonical_fingerprint(title, "pyroscope"),
        source=AutoIssue.SOURCE_PYROSCOPE,
        external_id=fingerprint,
        fingerprint=fingerprint,
        title=title,
        description=description,
        affected_files=[],
        severity=AutoIssue.SEVERITY_MEDIUM,
        priority_score=float(score),
        occurrence_count=max(1, int(total_self_ns / 1e6)),
        category_key="tooling",
    )
    return outcome


def _score_and_upsert_hotspots(
    cands: list[PyroscopeCandidate], *, limit: int
) -> int:
    """Score candidates, sort, upsert top-K. Returns count promoted."""
    if not cands:
        return 0
    max_blast = max(c.right_self_ns for c in cands)
    scored = [
        (score_candidate(_candidate_for_score(pc, max_blast)), pc)
        for pc in cands
    ]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    promoted = 0
    for score, pc in scored[:limit]:
        _upsert_hotspot_row(score, pc)
        promoted += 1
    return promoted


def pick_pyroscope_hotspots(
    *,
    server: str | None = None,
    applications: tuple[str, ...] = (
        "xf-linker-backend",
        "xf-linker-celery-default",
        "xf-linker-celery-pipeline",
        "xf-linker-celery-beat",
    ),
    limit: int = _MAX_PER_RUN,
) -> dict:
    """Top-level entrypoint — fetch single-period flamegraphs, promote
    hotspots above threshold to AutoIssue rows.

    No-ops cleanly when the Pyroscope server is unreachable or returns
    nothing. Idempotent: hotspots use a separate fingerprint prefix
    (``hotspot::``) from regressions so the two detectors never collide
    on the ``(source, external_id)`` unique constraint.
    """
    server = server or os.environ.get("PYROSCOPE_SERVER_ADDRESS", "")
    if not server:
        return {"status": "skipped", "reason": "missing_pyroscope_server"}
    threshold_pct, window_s = _read_hotspot_settings()
    cands = _gather_hotspots(
        server,
        applications,
        threshold_pct=threshold_pct,
        window_s=window_s,
    )
    if not cands:
        return {"status": "ok", "hotspots_found": 0, "promoted": 0}
    app_cands, tooling_cands = _split_profiler_tooling_hotspots(cands)
    promoted = _score_and_upsert_hotspots(app_cands, limit=limit)
    tooling_promoted = 0
    if tooling_cands:
        _upsert_profiler_tooling_row(tooling_cands)
        tooling_promoted = 1
    logger.info(
        "[auto_issues.pyroscope_picker.hotspots] found=%d app=%d "
        "tooling=%d promoted=%d threshold_pct=%.1f window_s=%d",
        len(cands),
        len(app_cands),
        len(tooling_cands),
        promoted + tooling_promoted,
        threshold_pct,
        window_s,
    )
    return {
        "status": "ok",
        "hotspots_found": len(cands),
        "app_hotspots_found": len(app_cands),
        "profiler_tooling_found": len(tooling_cands),
        "promoted": promoted + tooling_promoted,
        "profiler_tooling_promoted": tooling_promoted,
        "threshold_pct": threshold_pct,
        "window_seconds": window_s,
    }
