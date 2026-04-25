"""OHEM (Online Hard Example Mining) — pick #46.

Reference
---------
Shrivastava, A., Gupta, A., & Girshick, R. (2016). "Training
Region-based Object Detectors with Online Hard Example Mining."
*CVPR 2016*, pp. 761-769.

Goal
----
Per minibatch, sort training examples by their per-example loss and
keep only the top-K (highest-loss) examples for the gradient step.
Skips easy examples that the model already classifies confidently,
focusing capacity on the genuinely hard cases.

This is pure-Python: the algorithm is "sort by loss, take top-K".
Works on any iterable of ``(item, loss)`` pairs.
"""

from __future__ import annotations

from typing import Sequence, TypeVar

T = TypeVar("T")


def select_hard_examples(
    items_with_losses: Sequence[tuple[T, float]],
    *,
    keep_top_k: int,
) -> list[tuple[T, float]]:
    """Return the *keep_top_k* highest-loss ``(item, loss)`` pairs.

    Cold-start safe: empty input → ``[]``; ``keep_top_k <= 0`` →
    ``[]``; ``keep_top_k > len`` → returns the whole input sorted by
    loss desc.

    The output is sorted by loss descending so the caller can take
    a deterministic prefix or shuffle as needed.
    """
    if keep_top_k <= 0 or not items_with_losses:
        return []
    sorted_pairs = sorted(items_with_losses, key=lambda pair: -float(pair[1]))
    return sorted_pairs[:keep_top_k]
