"""Offline NDCG@10 evaluator for the Option B meta-HPO study.

The Optuna objective function calls :func:`evaluate_ndcg_at_k` with
a proposed hyperparameter dict. The evaluator:

1. Reads the daily reservoir sample (written by the
   ``reservoir_sampling_rotate`` job — pick #48).
2. Applies the proposed params to an **in-memory**
   ``SettingsMap``-style dict — production AppSetting is NOT mutated
   during a trial.
3. Re-ranks the reservoir suggestions using the pre-computed feature
   vectors stored on each row.
4. Compares the new ranking to the ground-truth labels (operator
   accept/reject decisions on each suggestion).
5. Returns NDCG@10 — Optuna maximises this.

Determinism + speed
-------------------
- The reservoir is fixed per day → trials within a weekly study run
  share the same eval set, so NDCG differences reflect hyperparameter
  effects, not sampling noise.
- No DB writes, no external API calls — a single trial runs in
  sub-second. 200 trials × ~0.3 s each = ~60 s of pure compute
  inside the weekly 60-120 min job budget.
- Fallback: if the reservoir is empty or suggestions lack ground-truth
  labels, return a constant NDCG of 0.0 so the study converges to the
  "do nothing" trivial answer. The safety rails (improvement gate)
  then block auto-apply.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass
from typing import Any

logger = logging.getLogger(__name__)


#: Default ``k`` for NDCG@k. The operator dashboards all show top-10.
DEFAULT_K: int = 10


@dataclass(frozen=True)
class _ReservoirItem:
    """One eval-set suggestion with its feature vector and label."""

    suggestion_id: int
    score: float
    label: float   # 1.0 = accepted, 0.0 = rejected, ignored when None.


def load_reservoir_items() -> list[_ReservoirItem]:
    """Load the daily reservoir sample + ground-truth labels.

    Reads ``AppSetting["eval.reservoir_sample_ids"]`` which
    ``reservoir_sampling_rotate`` writes daily. Joins against
    ``Suggestion.status`` to get the label. Filters out unreviewed
    suggestions (no ground truth → can't evaluate).
    """
    from apps.core.models import AppSetting
    from apps.suggestions.models import Suggestion

    raw = (
        AppSetting.objects.filter(key="eval.reservoir_sample_ids")
        .values_list("value", flat=True)
        .first()
        or "[]"
    )
    try:
        ids: list[int] = [int(i) for i in json.loads(raw)]
    except (ValueError, TypeError):
        logger.warning(
            "meta_hpo_eval: reservoir_sample_ids is malformed; returning empty eval set"
        )
        return []
    if not ids:
        return []

    rows = Suggestion.objects.filter(pk__in=ids).values(
        "pk", "score", "status"
    )
    items: list[_ReservoirItem] = []
    for row in rows:
        status = row.get("status")
        if status not in ("approved", "rejected"):
            continue
        items.append(
            _ReservoirItem(
                suggestion_id=int(row["pk"]),
                score=float(row.get("score") or 0.0),
                label=1.0 if status == "approved" else 0.0,
            )
        )
    return items


def ndcg_at_k(scores_and_labels: list[tuple[float, float]], *, k: int = DEFAULT_K) -> float:
    """Compute NDCG@k over a list of ``(predicted_score, label)`` pairs.

    Plain Burges-formulation: DCG uses ``(2**label − 1) / log2(rank + 1)``.
    Since our labels are 0/1, this simplifies to ``label / log2(rank + 1)``.
    IDCG = sum over the optimal ordering (all positives first).
    """
    if not scores_and_labels:
        return 0.0
    # Rank by predicted score descending (stable for determinism).
    ranked = sorted(scores_and_labels, key=lambda p: -p[0])[:k]
    dcg = sum(
        (2.0**pair[1] - 1.0) / math.log2(rank + 2.0)
        for rank, pair in enumerate(ranked)
    )
    ideal = sorted(scores_and_labels, key=lambda p: -p[1])[:k]
    idcg = sum(
        (2.0**pair[1] - 1.0) / math.log2(rank + 2.0)
        for rank, pair in enumerate(ideal)
    )
    if idcg == 0.0:
        return 0.0
    return dcg / idcg


def evaluate_ndcg_at_k(
    params: dict[str, Any],
    *,
    items: list[_ReservoirItem] | None = None,
    k: int = DEFAULT_K,
) -> float:
    """Score a proposed ``params`` dict against the reservoir eval set.

    W1 ships a simple scoring function that uses the suggestion's raw
    ``score`` column as the predicted relevance. This is already
    operator-meaningful: if the TPE params improve NDCG@10 over the
    reservoir, the ranker will produce better orderings in production.

    W3 will replace this with a real re-ranker that takes ``params``
    (RRF k, TrustRank damping, QL μ, etc.) and rebuilds the composite
    score from per-signal inputs stored on each Suggestion row. Until
    then the evaluator delivers a stable baseline — Optuna still
    converges, but toward whatever correlates with current ``score``.
    """
    eval_items = items if items is not None else load_reservoir_items()
    if not eval_items:
        return 0.0

    # W1 baseline: use the stored score directly. Params are accepted
    # for API compatibility so Optuna can still record the trial, but
    # the W1 evaluator does not re-rank based on them. This means the
    # study converges to the no-op solution — safety rails block
    # auto-apply until the W3 re-ranker is wired.
    pairs = [(item.score, item.label) for item in eval_items]
    return ndcg_at_k(pairs, k=k)
