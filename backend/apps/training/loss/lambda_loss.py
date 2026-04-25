"""LambdaLoss — pick #44.

Reference
---------
Wang, X., Li, C., Golbandi, N., Bendersky, M., & Najork, M. (2018).
"The LambdaLoss Framework for Ranking Metric Optimization."
*Proceedings of the 27th ACM CIKM*, pp. 1313-1322.

Goal
----
Listwise pairwise ranking loss that approximates NDCG. The
LambdaRank gradient — pioneered by Burges (2005) — weights each
pairwise loss term by the change in NDCG that swapping the pair
would induce. LambdaLoss formalises this as a proper loss function
that's differentiable w.r.t. the model scores.

This is a hand-rolled NumPy implementation per Wang et al. §3 — no
TensorFlow Ranking dependency. Operates on per-query lists of
(score, label) tuples.

Cold-start safe: empty list → 0.0. Single item → 0.0 (no pairs
to compare). All-equal labels → 0.0 (no NDCG signal).
"""

from __future__ import annotations

import math
from typing import Sequence


def _dcg(labels_in_order: Sequence[float]) -> float:
    """DCG at full depth — sum of ``(2^l - 1) / log2(rank+1)``."""
    return sum(
        (math.pow(2.0, label) - 1.0) / math.log2(rank + 2.0)
        for rank, label in enumerate(labels_in_order)
    )


def _ndcg(labels_in_order: Sequence[float]) -> float:
    """Normalised DCG — DCG / IdealDCG."""
    if not labels_in_order:
        return 0.0
    ideal = _dcg(sorted(labels_in_order, reverse=True))
    if ideal <= 0:
        return 0.0
    return _dcg(labels_in_order) / ideal


def lambda_loss(
    scores: Sequence[float],
    labels: Sequence[float],
) -> float:
    """Compute LambdaLoss for a single query's (scores, labels).

    Formula::

        L = Σ_{i, j: y_i > y_j} log(1 + exp(-σ * (s_i - s_j)))
            * |ΔNDCG_ij|

    σ is fixed at 1.0 (Wang et al. §4 — operators rarely tune this).

    Cold-start safe at every input shape.
    """
    if len(scores) != len(labels):
        raise ValueError(
            f"scores ({len(scores)}) and labels ({len(labels)}) must align"
        )
    n = len(scores)
    if n < 2:
        return 0.0

    # Build the index ordering induced by current scores so we can
    # compute the NDCG of the *current* ranking.
    score_order = sorted(range(n), key=lambda i: -scores[i])
    labels_in_score_order = [float(labels[i]) for i in score_order]
    ideal = _dcg(sorted(labels_in_score_order, reverse=True))
    if ideal <= 0:
        return 0.0

    # Cache discount factors for efficiency.
    discount = [1.0 / math.log2(rank + 2.0) for rank in range(n)]
    rank_of: dict[int, int] = {idx: rank for rank, idx in enumerate(score_order)}
    gain = [math.pow(2.0, float(labels[i])) - 1.0 for i in range(n)]

    total = 0.0
    sigma = 1.0
    for i in range(n):
        for j in range(n):
            if labels[i] <= labels[j]:
                continue
            # |ΔNDCG_ij| = the NDCG change if i and j swapped places.
            ri, rj = rank_of[i], rank_of[j]
            delta_ndcg = abs(
                (gain[i] - gain[j]) * (discount[ri] - discount[rj]) / ideal
            )
            # log1p(exp(-σ * (s_i - s_j))) — the pairwise logistic
            # loss component, same as RankNet's cross-entropy.
            margin = sigma * (float(scores[i]) - float(scores[j]))
            try:
                pair_loss = math.log1p(math.exp(-margin))
            except OverflowError:
                pair_loss = -margin if margin < 0 else 0.0
            total += delta_ndcg * pair_loss
    return float(total)


def lambda_rank_loss(
    scores: Sequence[float],
    labels: Sequence[float],
) -> float:
    """Alias for :func:`lambda_loss` — naming-compat with literature."""
    return lambda_loss(scores, labels)
