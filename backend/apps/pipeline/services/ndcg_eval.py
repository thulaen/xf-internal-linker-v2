"""Automated NDCG@K eval for the production ranker — paper-backed.

Goal
----
Answer "is the ranker actually any good?" without manual labelling.
Operators already label every suggestion they review (``approved`` =
positive, ``rejected`` = negative). This module turns that free
label stream into a daily NDCG readout on the dashboard.

References
----------
- Järvelin, K., & Kekäläinen, J. (2002). "Cumulated gain-based
  evaluation of IR techniques." *ACM TOIS*, 20(4), 422-446.
  Canonical NDCG@K definition; this module reuses
  :func:`apps.pipeline.services.meta_hpo_eval.ndcg_at_k`.
- Buckley, C., & Voorhees, E. M. (2004). "Retrieval evaluation with
  incomplete information." *SIGIR*, 25-32. Pooling: when only a
  fraction of the corpus is judged, evaluate against the union of
  what the rankers actually surfaced. Our pool = the reviewed
  Suggestion set in the lookback window.
- Sanderson, M. (2010). "Test collection based evaluation of
  information retrieval systems." *Found. Trends Inf. Retr.*,
  4(4), 247-375. §5.2 minimum-test-set rule of thumb: ≥50 queries
  for basic NDCG, ≥200 for stable pairwise comparison.

Why this works for our use case
-------------------------------
The internal-linker review queue is a TREC-style assessment workflow:

- Each operator decision (approve/reject) is a relevance judgement.
- The candidate pool is fully judged for that operator session
  (every suggestion presented gets a status).
- ``score_final`` is the predicted ranking score the ranker produced
  for that suggestion *at the time it was presented*.

So computing NDCG@K is a one-pass aggregation: sort by
``score_final`` descending, gain = 1 if ``approved`` else 0,
discount = ``1 / log2(rank + 2)``. Identical to the canonical
Järvelin-Kekäläinen formula — no estimation, no extrapolation.

Cold-start safe: ``< 50`` reviewed pairs in the lookback window →
returns ``insufficient_data=True`` per Sanderson §5.2. Operator
sees an "approve more suggestions, then this reads" message
instead of a noisy NDCG number.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from typing import Sequence

from .meta_hpo_eval import ndcg_at_k

logger = logging.getLogger(__name__)


KEY_LATEST_RESULT = "ndcg_eval.latest.json"
KEY_LATEST_FITTED_AT = "ndcg_eval.fitted_at"

#: Sanderson 2010 §5.2 — basic NDCG floor. Below this, confidence
#: intervals are too wide to be useful.
SANDERSON_BASIC_FLOOR: int = 50

#: Sanderson 2010 §5.2 — stable pairwise-comparison floor. A vs B
#: NDCG comparisons need ≥ 200 queries to detect ≥ 5 % deltas at
#: p = 0.05. Below this, the confidence band still emits a number
#: but flags itself as wide.
SANDERSON_PAIRWISE_FLOOR: int = 200

#: Default lookback. 30 days roughly matches one operator-review
#: cycle on a busy site and avoids stale-feedback bias.
DEFAULT_LOOKBACK_DAYS: int = 30

#: NDCG cutoff. Mirrors ``meta_hpo_eval.DEFAULT_K`` and the
#: ``test_bench_*`` benchmarks.
DEFAULT_K: int = 10

#: Bootstrap iterations for the confidence band. 1000 is the
#: textbook default (Efron-Tibshirani 1993); 500 would be fine but
#: 1000 is fast enough.
DEFAULT_BOOTSTRAP_ITERATIONS: int = 1000

#: Bootstrap confidence level. 0.95 → returns the 2.5 / 97.5
#: percentiles. Mirrors what ``meta_hpo_eval`` uses.
DEFAULT_CONFIDENCE: float = 0.95


@dataclass(frozen=True)
class NdcgResult:
    """One NDCG@K reading over a reviewed-Suggestion sample."""

    ndcg: float
    sample_size: int
    k: int
    sufficient_data: bool
    sufficient_for_pairwise: bool
    confidence_lower: float
    confidence_upper: float
    message: str
    fitted_at: str | None = None
    breakdown_by_candidate_origin: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "ndcg": self.ndcg,
            "sample_size": self.sample_size,
            "k": self.k,
            "sufficient_data": self.sufficient_data,
            "sufficient_for_pairwise": self.sufficient_for_pairwise,
            "confidence_lower": self.confidence_lower,
            "confidence_upper": self.confidence_upper,
            "message": self.message,
            "fitted_at": self.fitted_at,
            "breakdown_by_candidate_origin": dict(
                self.breakdown_by_candidate_origin
            ),
        }


# ── Read API ──────────────────────────────────────────────────────


def load_latest() -> NdcgResult | None:
    """Return the most recent persisted NDCG eval, or ``None`` on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return None
    row = AppSetting.objects.filter(key=KEY_LATEST_RESULT).first()
    if row is None or not row.value:
        return None
    try:
        payload = json.loads(row.value)
    except (TypeError, ValueError):
        logger.warning("ndcg_eval: malformed latest-result JSON")
        return None
    return NdcgResult(
        ndcg=float(payload.get("ndcg", 0.0)),
        sample_size=int(payload.get("sample_size", 0)),
        k=int(payload.get("k", DEFAULT_K)),
        sufficient_data=bool(payload.get("sufficient_data", False)),
        sufficient_for_pairwise=bool(payload.get("sufficient_for_pairwise", False)),
        confidence_lower=float(payload.get("confidence_lower", 0.0)),
        confidence_upper=float(payload.get("confidence_upper", 0.0)),
        message=str(payload.get("message", "")),
        fitted_at=payload.get("fitted_at"),
        breakdown_by_candidate_origin=dict(
            payload.get("breakdown_by_candidate_origin") or {}
        ),
    )


# ── Sufficient-data gate (Sanderson §5.2) ────────────────────────


def sufficient_data(
    sample_size: int,
) -> tuple[bool, bool, str]:
    """Return ``(usable, pairwise_ready, message)``.

    Three regimes per Sanderson 2010 §5.2:

    - ``< SANDERSON_BASIC_FLOOR`` (50): NDCG is noise; both flags False.
    - ``[BASIC_FLOOR, PAIRWISE_FLOOR)``: NDCG is informative, but A/B
      comparisons need a wider confidence band — usable=True,
      pairwise_ready=False.
    - ``≥ PAIRWISE_FLOOR`` (200): both flags True.
    """
    if sample_size < SANDERSON_BASIC_FLOOR:
        return (
            False,
            False,
            f"Only {sample_size} reviewed suggestions in window. "
            f"Need ≥ {SANDERSON_BASIC_FLOOR} (Sanderson 2010 §5.2). "
            "Approve more, then this reads.",
        )
    if sample_size < SANDERSON_PAIRWISE_FLOOR:
        return (
            True,
            False,
            f"{sample_size} reviewed suggestions — informative but "
            f"confidence intervals are wide. Reach "
            f"≥ {SANDERSON_PAIRWISE_FLOOR} for stable pairwise comparison "
            "(Sanderson 2010 §5.2).",
        )
    return (
        True,
        True,
        f"{sample_size} reviewed suggestions — sufficient for stable "
        "pairwise comparison.",
    )


# ── Bootstrap CI on NDCG@K ────────────────────────────────────────


def bootstrap_ndcg_ci(
    scores_and_labels: Sequence[tuple[float, float]],
    *,
    k: int = DEFAULT_K,
    iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int | None = 0,
) -> tuple[float, float]:
    """Return ``(lower, upper)`` percentile bounds on NDCG@K.

    Standard non-parametric bootstrap (Efron-Tibshirani 1993):
    resample with replacement N times, compute NDCG on each
    resample, take percentiles.

    ``confidence`` is the central mass — 0.95 returns the 2.5 / 97.5
    percentile pair.
    """
    import random

    n = len(scores_and_labels)
    if n < 2:
        return 0.0, 0.0
    rng = random.Random(seed)
    samples: list[float] = []
    pool = list(scores_and_labels)
    for _ in range(iterations):
        resample = [pool[rng.randrange(n)] for _ in range(n)]
        samples.append(ndcg_at_k(resample, k=k))
    samples.sort()
    lo_idx = int((1.0 - confidence) / 2.0 * iterations)
    hi_idx = iterations - lo_idx - 1
    lo_idx = max(0, min(iterations - 1, lo_idx))
    hi_idx = max(0, min(iterations - 1, hi_idx))
    return samples[lo_idx], samples[hi_idx]


# ── Core eval ─────────────────────────────────────────────────────


def _pairs_from_reviewed_suggestions(
    *, days_back: int = DEFAULT_LOOKBACK_DAYS
) -> tuple[list[tuple[float, float]], dict[str, list[tuple[float, float]]]]:
    """Read approved/rejected Suggestions in the lookback window.

    Returns:

    - ``(score_final, label)`` pairs — label = 1.0 if approved, 0.0
      if rejected.
    - Per-candidate-origin breakdown (e.g. ``"semantic"``,
      ``"graph_signal_node2vec"``) → its own ``(score, label)`` list.
      Lets the dashboard show which retriever's candidates the
      operator actually approves more.
    """
    from datetime import timedelta

    from django.utils import timezone

    from apps.suggestions.models import Suggestion

    cutoff = timezone.now() - timedelta(days=days_back)
    rows = list(
        Suggestion.objects.filter(
            updated_at__gte=cutoff,
            status__in=["approved", "rejected"],
        ).values("score_final", "status", "candidate_origin")
    )

    pairs: list[tuple[float, float]] = []
    by_origin: dict[str, list[tuple[float, float]]] = {}
    for row in rows:
        score = float(row.get("score_final") or 0.0)
        label = 1.0 if row["status"] == "approved" else 0.0
        pairs.append((score, label))
        origin = (row.get("candidate_origin") or "unknown").strip() or "unknown"
        by_origin.setdefault(origin, []).append((score, label))
    return pairs, by_origin


def evaluate(
    *,
    days_back: int = DEFAULT_LOOKBACK_DAYS,
    k: int = DEFAULT_K,
    bootstrap_iterations: int = DEFAULT_BOOTSTRAP_ITERATIONS,
    confidence: float = DEFAULT_CONFIDENCE,
) -> NdcgResult:
    """Compute NDCG@K over the reviewed-Suggestion stream.

    Cold-start safe: returns a result with ``sufficient_data=False``
    when fewer than :data:`SANDERSON_BASIC_FLOOR` reviewed
    suggestions exist in the window.
    """
    from django.utils import timezone

    pairs, by_origin = _pairs_from_reviewed_suggestions(days_back=days_back)
    n = len(pairs)
    usable, pairwise_ready, message = sufficient_data(n)

    if not usable:
        return NdcgResult(
            ndcg=0.0,
            sample_size=n,
            k=k,
            sufficient_data=False,
            sufficient_for_pairwise=False,
            confidence_lower=0.0,
            confidence_upper=0.0,
            message=message,
            fitted_at=timezone.now().isoformat(),
            breakdown_by_candidate_origin={},
        )

    score = ndcg_at_k(pairs, k=k)
    lo, hi = bootstrap_ndcg_ci(
        pairs,
        k=k,
        iterations=bootstrap_iterations,
        confidence=confidence,
    )

    # Per-origin breakdown — only for origins with ≥ basic floor.
    origin_breakdown: dict[str, float] = {}
    for origin, origin_pairs in by_origin.items():
        if len(origin_pairs) < SANDERSON_BASIC_FLOOR:
            continue
        origin_breakdown[origin] = ndcg_at_k(origin_pairs, k=k)

    return NdcgResult(
        ndcg=score,
        sample_size=n,
        k=k,
        sufficient_data=True,
        sufficient_for_pairwise=pairwise_ready,
        confidence_lower=lo,
        confidence_upper=hi,
        message=message,
        fitted_at=timezone.now().isoformat(),
        breakdown_by_candidate_origin=origin_breakdown,
    )


def evaluate_and_persist(
    *,
    days_back: int = DEFAULT_LOOKBACK_DAYS,
    k: int = DEFAULT_K,
) -> NdcgResult:
    """Run the eval and persist the result to AppSetting for the dashboard."""
    from apps.core.models import AppSetting

    result = evaluate(days_back=days_back, k=k)
    AppSetting.objects.update_or_create(
        key=KEY_LATEST_RESULT,
        defaults={
            "value": json.dumps(result.to_dict(), separators=(",", ":")),
            "description": (
                "Latest NDCG@K eval — Järvelin-Kekäläinen 2002 ACM TOIS, "
                "Sanderson 2010 FnTIR §5.2 sample-size gate. Refit daily "
                "by ndcg_smoke_test."
            ),
        },
    )
    AppSetting.objects.update_or_create(
        key=KEY_LATEST_FITTED_AT,
        defaults={
            "value": result.fitted_at or "",
            "description": "Timestamp of the most recent NDCG eval run.",
        },
    )
    return result
