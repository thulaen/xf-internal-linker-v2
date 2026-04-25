"""SWA (Stochastic Weight Averaging) — pick #45.

Reference
---------
Izmailov, P., Podoprikhin, D., Garipov, T., Vetrov, D., & Wilson,
A. G. (2018). "Averaging Weights Leads to Wider Optima and Better
Generalization." *Proceedings of UAI 2018*.

Goal
----
Average the weights from multiple training epochs (typically the
last K) to produce a smoother, better-generalising model. Trivially
cheap at training time, no inference cost.

This is a tiny pure-Python helper: maintain a running average over
arbitrary parameter dicts. Designed to work with any model that
exposes a flat ``{name: tensor-or-array}`` mapping — torch, numpy,
plain-list — without depending on torch's ``AveragedModel`` (which
ties you to torch).
"""

from __future__ import annotations

from typing import Mapping

import numpy as np


class StochasticWeightAverager:
    """Running average over parameter dicts.

    Usage::

        swa = StochasticWeightAverager()
        for epoch in range(num_epochs):
            train_one_epoch(model)
            if epoch >= warmup_epochs:
                swa.add(model.state_dict())
        averaged = swa.snapshot()

    ``snapshot()`` returns the per-key arithmetic mean, suitable for
    loading back into a model. Cold-start safe: ``snapshot`` before
    any ``add`` returns ``{}``.
    """

    def __init__(self) -> None:
        self._sum: dict[str, np.ndarray] = {}
        self._count = 0

    @property
    def count(self) -> int:
        """Number of parameter dicts averaged so far."""
        return self._count

    def add(self, parameters: Mapping[str, object]) -> None:
        """Accumulate one parameter dict into the running sum.

        Each value is coerced to ``np.ndarray`` first so the helper
        works for torch tensors (which expose ``__array__``), numpy
        arrays, and plain lists alike.
        """
        for key, value in parameters.items():
            arr = np.asarray(value, dtype=float)
            if key not in self._sum:
                self._sum[key] = arr.copy()
            elif self._sum[key].shape != arr.shape:
                raise ValueError(
                    f"SWA: parameter '{key}' shape mismatch — "
                    f"prev {self._sum[key].shape} vs new {arr.shape}"
                )
            else:
                self._sum[key] += arr
        self._count += 1

    def snapshot(self) -> dict[str, np.ndarray]:
        """Return the per-key arithmetic mean.

        Cold-start safe: returns ``{}`` when no ``add`` has been
        called yet.
        """
        if self._count == 0:
            return {}
        return {key: arr / self._count for key, arr in self._sum.items()}

    def reset(self) -> None:
        """Discard all accumulated state."""
        self._sum.clear()
        self._count = 0
