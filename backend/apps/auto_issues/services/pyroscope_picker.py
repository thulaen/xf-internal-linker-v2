"""Pyroscope → AutoIssue picker — regression detection.

Reads Pyroscope's HTTP API and surfaces functions whose self-CPU time
grew ≥2× week-over-week AND account for ≥5 % of the total runtime in
the most recent 24 h window. Each surviving function becomes one
AutoIssue row with `source='pyroscope'` and a priority score from
``services.scoring``.

Design decisions (from SPEC § Open design decisions):
  - (d) We query 24h chunks instead of 7-day windows so a single API
    call can never exceed a few MB. Two queries: today + same-day-last-week.
  - We do NOT auto-assign (decision (c)); rows land as `status='open'`.

Pyroscope HTTP API used (OSS 1.9 — Phlare-derived):
  GET /pyroscope/render-diff?
      from=<unix-ts>&until=<unix-ts>&query=<labelset>
The diff endpoint returns left/right flamegraphs for week-over-week
comparison. We extract per-function totals from each side and compute
ratio = right_total / left_total (clamped to a minimum left_total to
avoid divide-by-zero noise).
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
    return hashlib.sha1(raw.encode()).hexdigest()[:16]


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
        "query": f"process_cpu:cpu:nanoseconds:cpu:nanoseconds{{service_name=\"{application}\"}}",
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
