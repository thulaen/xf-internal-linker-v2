"""Uncertainty sampling for review-queue ordering (Lewis & Gale 1994).

Reference
---------
Lewis, D. D. & Gale, W. A. (1994). "A sequential algorithm for training
text classifiers." *Proceedings of the 17th ACM SIGIR Conference*,
pp. 3-12.

Goal
----
Operators have a fixed daily review budget (say 50 suggestions). If we
show them the highest-confidence suggestions first, they waste attention
on cases the model already gets right. Uncertainty sampling flips it:
show the model's **least-confident** cases first — that's where human
judgement adds the most value and where each label best reduces future
model uncertainty.

Three strategies
----------------
The module implements all three of Lewis-Gale's classical strategies so
operators can A/B between them via the TPE meta-HPO job:

- ``least_confidence`` — ``uncertainty = 1 − max(P)``. Works for any
  number of classes. Intuitive: if the top-predicted class has 60 %
  probability, uncertainty is 40 %. Lewis & Gale 1994's default.
- ``margin`` — ``uncertainty = −(p_top1 − p_top2)``. Focuses on the
  *gap* between the best and second-best class. Smaller gap = more
  uncertain. Requires at least 2 classes in each row.
- ``entropy`` — ``uncertainty = −Σ p_i log(p_i)``. Maximum-entropy
  rows rank first. Most symmetric but also most sensitive to many
  low-probability classes.

The module is pure Python with a NumPy fast path — no new pip deps
beyond what's already installed.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from enum import Enum
from typing import Iterable, Sequence

import numpy as np


class Strategy(str, Enum):
    """Supported uncertainty strategies."""

    LEAST_CONFIDENCE = "least_confidence"
    MARGIN = "margin"
    ENTROPY = "entropy"


DEFAULT_STRATEGY: str = Strategy.LEAST_CONFIDENCE.value


@dataclass(frozen=True)
class UncertaintyScore:
    """One row's uncertainty score.

    ``uncertainty`` higher = more uncertain = review first.
    ``original_index`` is the row's position in the input, preserved
    so callers can map back to their own DataFrame / query set.
    """

    original_index: int
    uncertainty: float


def rank_by_uncertainty(
    probabilities: Iterable[Sequence[float]] | np.ndarray,
    *,
    strategy: str = DEFAULT_STRATEGY,
) -> list[int]:
    """Return original indices sorted most-uncertain first.

    Parameters
    ----------
    probabilities
        Either a 2-D array-like of class probabilities ``(N, C)`` or
        a 1-D iterable of *scalar* probabilities (interpreted as the
        binary-positive probability — the module builds the
        complement automatically for binary review use cases).
    strategy
        One of ``"least_confidence"``, ``"margin"``, ``"entropy"``.

    Returns
    -------
    List of original row indices, ordered most-uncertain first. Ties
    are broken stably (preserving input order) so the review queue is
    deterministic across runs on the same data.

    Raises
    ------
    ValueError
        On unknown strategy, or ``margin`` with fewer than 2 classes.
    """
    arr = _to_2d_probabilities(probabilities)
    scores = _score_all(arr, strategy=strategy)
    # argsort is stable in NumPy; negate to sort descending by score.
    order = np.argsort(-scores, kind="stable")
    return [int(i) for i in order]


def score(
    probabilities: Iterable[Sequence[float]] | np.ndarray,
    *,
    strategy: str = DEFAULT_STRATEGY,
) -> list[UncertaintyScore]:
    """Return per-row uncertainty scores preserving original indices.

    Useful when callers want to surface the uncertainty magnitude in
    the review UI ("this suggestion is 80 % uncertain") rather than
    only ordering.
    """
    arr = _to_2d_probabilities(probabilities)
    scores = _score_all(arr, strategy=strategy)
    return [
        UncertaintyScore(original_index=i, uncertainty=float(s))
        for i, s in enumerate(scores)
    ]


# ── Internals ──────────────────────────────────────────────────────


def _to_2d_probabilities(
    probabilities: Iterable[Sequence[float]] | np.ndarray,
) -> np.ndarray:
    arr = np.asarray(list(probabilities) if not isinstance(probabilities, np.ndarray) else probabilities, dtype=float)
    if arr.size == 0:
        return arr.reshape(0, 0)
    if arr.ndim == 1:
        # Binary case — build the (P, 1-P) pair per row so the
        # 2-class formulas below work without a special case.
        complement = 1.0 - arr
        return np.column_stack([arr, complement])
    if arr.ndim != 2:
        raise ValueError("probabilities must be 1-D or 2-D")
    return arr


def _score_all(arr: np.ndarray, *, strategy: str) -> np.ndarray:
    if arr.size == 0:
        return np.zeros(0, dtype=float)

    strategy_lc = strategy.lower()
    if strategy_lc == Strategy.LEAST_CONFIDENCE.value:
        return 1.0 - arr.max(axis=1)

    if strategy_lc == Strategy.MARGIN.value:
        if arr.shape[1] < 2:
            raise ValueError("margin strategy requires at least 2 classes")
        # Sort descending per row; uncertainty is -(p_top - p_second).
        partitioned = -np.sort(-arr, axis=1)
        top, second = partitioned[:, 0], partitioned[:, 1]
        return -(top - second)

    if strategy_lc == Strategy.ENTROPY.value:
        # Clip to avoid log(0); 1e-12 floor matches the project's
        # consistent "sane ε" used in query_likelihood and collocations.
        clipped = np.clip(arr, 1e-12, 1.0)
        return -np.sum(clipped * np.log(clipped), axis=1)

    raise ValueError(
        f"unknown strategy {strategy!r} — choose one of "
        f"{[s.value for s in Strategy]}"
    )
