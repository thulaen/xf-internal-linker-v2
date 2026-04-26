"""Platt scaling — logistic calibration of raw ranker scores.

Reference
---------
Platt, J. C. (1999). "Probabilistic outputs for support vector machines
and comparisons to regularized likelihood methods." *Advances in Large
Margin Classifiers*, pp. 61-74. MIT Press.

Goal
----
Turn a raw, uncalibrated ranker score ``f(d)`` into a calibrated
probability ``P(relevant | f(d))`` that operators and downstream
code can read as a percentage. Platt's original paper fits a
two-parameter sigmoid::

    P(y = 1 | f) = 1 / ( 1 + exp( A * f + B ) )

by maximum-likelihood on a held-out set of ``(score, binary_label)``
pairs. The parameters ``A`` (slope) and ``B`` (bias) come out of a
convex optimisation — no hyperparameter tuning needed.

Why not :class:`sklearn.calibration.CalibratedClassifierCV`?
  That class wraps a classifier's ``.predict_proba`` pipeline; the
  linker's ranker is a pure score function with no sklearn estimator
  object. Using scipy to solve the 2-parameter logistic fit directly
  gives us a tiny helper (< 50 SLOC) that's trivially testable and
  reuses the scipy dep already shipped for ``weight_tuner.py``.

Platt's original paper also recommends clipping the label targets to
``(1 - 1/(N_pos + 2), 1/(N_neg + 2))`` instead of raw ``0/1`` to
avoid numerical saturation in the optimiser — we implement that
adjustment exactly as in his §4.

The module is deterministic for the same inputs and leaves the
caller in charge of picking the calibration set (held-out vs
cross-validated vs bootstrap — Platt discusses trade-offs in §3).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Iterable, Sequence

import numpy as np
from scipy.optimize import minimize


#: Initial guess for slope and bias. ``A = 0, B = log((N+1)/(P+1))``
#: from Platt's §4 — starts the optimiser at the trivial
#: "predict the prior" model, which is always within the basin of
#: the MLE.
_INITIAL_SLOPE: float = 0.0


@dataclass(frozen=True)
class PlattCalibration:
    """Fitted logistic sigmoid mapping scores → probabilities.

    Attributes
    ----------
    slope
        The ``A`` parameter. Typically negative — higher raw scores
        should correspond to higher probability, and the sigmoid
        formula uses ``exp(A*f + B)`` in its denominator.
    bias
        The ``B`` parameter.
    n_positives, n_negatives
        Training-set class counts (stored for diagnostics).
    """

    slope: float
    bias: float
    n_positives: int
    n_negatives: int

    def predict(self, score: float) -> float:
        """Return the calibrated probability for a single *score*."""
        return _sigmoid(self.slope * score + self.bias)

    def predict_many(self, scores: Sequence[float]) -> list[float]:
        """Vectorised version of :meth:`predict`."""
        arr = np.asarray(scores, dtype=float)
        logits = self.slope * arr + self.bias
        # Use numpy's vectorised expit-equivalent for stability.
        return list(1.0 / (1.0 + np.exp(logits)))


def fit(
    *,
    scores: Iterable[float],
    labels: Iterable[int],
) -> PlattCalibration:
    """Fit Platt parameters on ``(score, label)`` pairs.

    Labels must be 0 or 1. Lengths must match. ``scores`` can be any
    real-valued numbers — Platt's original paper was written for
    SVM decision values, but the method works on any score.

    Raises
    ------
    ValueError
        If the two inputs have different lengths, if any label is
        not 0/1, or if the data contains only one class (the sigmoid
        fit is degenerate).
    """
    score_arr = np.asarray(list(scores), dtype=float)
    label_arr = np.asarray(list(labels), dtype=int)

    if score_arr.shape != label_arr.shape:
        raise ValueError("scores and labels must have the same length")
    if score_arr.size == 0:
        raise ValueError("need at least one (score, label) pair")
    if not np.all(np.isin(label_arr, (0, 1))):
        raise ValueError("labels must be 0 or 1")

    n_pos = int(np.sum(label_arr == 1))
    n_neg = int(np.sum(label_arr == 0))
    if n_pos == 0 or n_neg == 0:
        raise ValueError("need both positive and negative examples to fit a sigmoid")

    # Platt §4 — soft targets that avoid saturation at y = 0 / y = 1.
    t_pos = (n_pos + 1) / (n_pos + 2)
    t_neg = 1.0 / (n_neg + 2)
    targets = np.where(label_arr == 1, t_pos, t_neg)

    # Negative log-likelihood of the sigmoid, computed with a
    # numerically stable log(1 + exp(x)) via ``np.logaddexp``.
    def objective(params: np.ndarray) -> float:
        a, b = params
        logits = a * score_arr + b
        # For t=1: loss = log(1 + exp(logits))  = logaddexp(0, logits)
        # For t=0: loss = log(1 + exp(-logits)) = logaddexp(0, -logits)
        # Blended by soft targets: t * logaddexp(0, logits) +
        #                         (1 - t) * logaddexp(0, -logits)
        pos_term = np.logaddexp(0.0, logits) * targets
        neg_term = np.logaddexp(0.0, -logits) * (1.0 - targets)
        return float(np.sum(pos_term + neg_term))

    initial_bias = math.log((n_neg + 1) / (n_pos + 1))
    result = minimize(
        objective,
        x0=np.array([_INITIAL_SLOPE, initial_bias]),
        method="L-BFGS-B",
    )
    a_fit, b_fit = float(result.x[0]), float(result.x[1])
    return PlattCalibration(
        slope=a_fit,
        bias=b_fit,
        n_positives=n_pos,
        n_negatives=n_neg,
    )


# ── Helpers ────────────────────────────────────────────────────────


def _sigmoid(logit: float) -> float:
    """Numerically stable 1 / (1 + exp(logit)).

    For ``logit`` very positive, ``exp(logit)`` overflows; we short-circuit
    to the asymptote. Same story for very negative values.
    """
    if logit >= 35.0:
        return 0.0
    if logit <= -35.0:
        return 1.0
    return 1.0 / (1.0 + math.exp(logit))
