"""Pure scoring functions for the daily issue picker.

Python reference implementation of the C++ kernel spec at
``docs/CPP-DAILY-ISSUE-PICKER-SPEC.md``. The five factors and their
research sources are documented there in full. The C++ version replaces
this module as a hot-path optimisation later; until then this is the
production code path.

Every function is pure, side-effect free, and tested in
``backend/apps/auto_issues/tests_scoring.py``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from apps.auto_issues.models import AutoIssue


@dataclass(frozen=True)
class ScoringWeights:
    """Weights summing to 1.0 — see SPEC § Recommended starting weights."""

    severity: float = 0.35
    recency: float = 0.20
    recurrence: float = 0.20
    blast: float = 0.15
    cost_inv: float = 0.10


# Severity prior table (SPEC factor 1 — ITIL / CMU SEI 2003-TR-002).
_SEV_TABLE_GLITCHTIP = {
    AutoIssue.SEVERITY_CRITICAL: 1.00,
    AutoIssue.SEVERITY_HIGH: 0.85,
    AutoIssue.SEVERITY_MEDIUM: 0.60,
    AutoIssue.SEVERITY_LOW: 0.20,
}
_SEV_TABLE_PYROSCOPE = {
    AutoIssue.SEVERITY_CRITICAL: 0.90,
    AutoIssue.SEVERITY_HIGH: 0.75,
    AutoIssue.SEVERITY_MEDIUM: 0.50,
    AutoIssue.SEVERITY_LOW: 0.10,
}
_SEV_TABLE_AGENT = {
    AutoIssue.SEVERITY_CRITICAL: 0.80,
    AutoIssue.SEVERITY_HIGH: 0.60,
    AutoIssue.SEVERITY_MEDIUM: 0.40,
    AutoIssue.SEVERITY_LOW: 0.10,
}
_SEV_TABLES = {
    AutoIssue.SOURCE_GLITCHTIP: _SEV_TABLE_GLITCHTIP,
    AutoIssue.SOURCE_PYROSCOPE: _SEV_TABLE_PYROSCOPE,
    AutoIssue.SOURCE_AGENT: _SEV_TABLE_AGENT,
}

# Recency exponential decay (SPEC factor 2 — Newell & Rosenbloom 1981).
_RECENCY_TAU_DAYS = 7.0

# Regression boost multiplier (SPEC factor 3 — STRIDE / Howard & LeBlanc 2003).
_REGRESSION_MULTIPLIER = 1.5


def severity_factor(source: str, severity: str) -> float:
    """Return SEV ∈ [0, 1] for (source, severity).

    Falls back to 0.0 for unknown combos so the score still computes.
    """
    return _SEV_TABLES.get(source, {}).get(severity, 0.0)


def recency_factor(last_seen: datetime, *, now: datetime | None = None) -> float:
    """Return REC = exp(-(now - last_seen) / tau).

    `tau = 7 days`. An issue last seen 14 days ago gets ~0.14; 30 days
    gets ~0.014. Stops the picker chasing zombies.
    """
    now = now or datetime.now(timezone.utc)
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    days_ago = max(0.0, (now - last_seen).total_seconds() / 86400.0)
    return math.exp(-days_ago / _RECENCY_TAU_DAYS)


def regression_factor(*, fingerprint: str, last_seen: datetime) -> float:
    """Return REG ∈ {0.0, 1.0}.

    Looks up `auto_issues_autoissue` for any prior `resolved` row sharing
    the fingerprint. If one exists AND `last_seen > resolved_at`, the
    issue regressed — return 1.0. Otherwise 0.0.
    """
    if last_seen.tzinfo is None:
        last_seen = last_seen.replace(tzinfo=timezone.utc)
    prior = (
        AutoIssue.objects
        .filter(fingerprint=fingerprint, status=AutoIssue.STATUS_RESOLVED)
        .order_by("-resolved_at")
        .first()
    )
    if prior is None or prior.resolved_at is None:
        return 0.0
    resolved_at = prior.resolved_at
    if resolved_at.tzinfo is None:
        resolved_at = resolved_at.replace(tzinfo=timezone.utc)
    return 1.0 if last_seen > resolved_at else 0.0


def blast_factor(observed: float, *, max_observed: float) -> float:
    """Return BLAST = observed / max_observed clamped to [0, 1].

    `observed` is source-specific:
    - GlitchTip: count of distinct culprit (module:function) pairs.
    - Pyroscope: total wall-clock time for this function (ms).
    - Agent find: count of files in `affected_files`.
    """
    if max_observed <= 0:
        return 0.0
    return min(1.0, observed / max_observed)


def cost_inv_factor(num_files: int) -> float:
    """Return COST_INV = 1 / (1 + log(1 + N)) (SPEC factor 5).

    A one-file fix → ≈ 1.0; five-file → ≈ 0.36; fifty-file → ≈ 0.20.
    Penalises sprawling fixes; same shape as the AIC complexity term.
    """
    return 1.0 / (1.0 + math.log(1.0 + max(0, num_files)))


@dataclass(frozen=True)
class Candidate:
    """One row in the daily picker's input list — pure data."""

    source: str
    external_id: str
    fingerprint: str
    severity: str
    last_seen: datetime
    blast_observed: float
    blast_max: float
    num_affected_files: int


def score_candidate(
    cand: Candidate,
    *,
    weights: ScoringWeights = ScoringWeights(),
    now: datetime | None = None,
) -> float:
    """Apply the 5-factor blend and the regression multiplier."""
    sev = severity_factor(cand.source, cand.severity)
    rec = recency_factor(cand.last_seen, now=now)
    reg = regression_factor(
        fingerprint=cand.fingerprint, last_seen=cand.last_seen
    )
    blast = blast_factor(cand.blast_observed, max_observed=cand.blast_max)
    cost = cost_inv_factor(cand.num_affected_files)

    base = (
        weights.severity * sev
        + weights.recency * rec
        + weights.recurrence * reg
        + weights.blast * blast
        + weights.cost_inv * cost
    )
    if reg == 1.0:
        return min(1.0, base * _REGRESSION_MULTIPLIER)
    return base


def top_k(candidates: list[Candidate], k: int = 10) -> list[Candidate]:
    """Return the k highest-scored candidates in descending priority.

    Pure-Python equivalent of `std::nth_element` followed by `sort` of the
    top-K (SPEC § Top-K selection). For our typical N (<1000), Python's
    `sorted` with reverse=True is O(N log N) but K=10 is constant; the
    runtime cost is dominated by the score function, not the sort.
    """
    if k <= 0:
        return []
    scored = [(score_candidate(c), c) for c in candidates]
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [c for _, c in scored[:k]]


def auto_close_stale_threshold(
    *, idle_days: int = 30, score_floor: float = 0.3
) -> tuple[timedelta, float]:
    """Return the cutoffs for `close_stale_issues` (SPEC § Anti-bloat).

    A row is stale when `last_seen < now - idle_days` AND
    `priority_score < score_floor`. Returned as (timedelta, float) so
    callers can build a single ORM filter.
    """
    return (timedelta(days=idle_days), score_floor)
