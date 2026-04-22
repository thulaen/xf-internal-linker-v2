"""Split-conformal prediction (Vovk-Gammerman-Shafer 2005).

Reference
---------
Vovk, V., Gammerman, A. & Shafer, G. (2005). *Algorithmic Learning in
a Random World.* Springer. ISBN 978-0-387-00152-4. Chapter 4 — inductive
conformal prediction.

Goal
----
Attach a **distribution-free** confidence interval to a point prediction:
given a calibration set of ``(score, label)`` pairs drawn from the same
distribution as the test inputs, compute a quantile of the nonconformity
scores. The resulting ``[score − q, score + q]`` band has guaranteed
coverage of at least ``1 − α`` — no assumptions on the data distribution
beyond exchangeability.

Plain English: if ``α = 0.1`` and the calibration set was fair, 90 % of
new labels will fall inside the predicted band.

Composition with ACI (pick #52)
-------------------------------
Vanilla split conformal assumes exchangeability. Real-world data drifts.
:mod:`apps.pipeline.services.adaptive_conformal_inference` wraps this
module to nudge ``α`` online so long-run coverage stays at target even
under arbitrary drift.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Sequence

import numpy as np


#: Standard 90 % confidence band. Matches the pick-50 spec default and
#: the ACI target (pick-52). Operators widen / tighten via AppSetting.
DEFAULT_ALPHA: float = 0.10


@dataclass(frozen=True)
class ConformalInterval:
    """One prediction's confidence band.

    ``half_width`` is the quantile magnitude used to build the band;
    ``alpha`` is the miscoverage target at fit time (``1 - alpha`` is
    the coverage). Retained so operators can debug shrink / widen
    behaviour by inspecting the interval dataclass directly.
    """

    predicted: float
    lower: float
    upper: float
    half_width: float
    alpha: float

    @property
    def width(self) -> float:
        return self.upper - self.lower


@dataclass(frozen=True)
class ConformalCalibration:
    """Fitted conformal quantile with metadata for audit."""

    alpha: float
    half_width: float
    calibration_set_size: int

    def predict_interval(self, score: float) -> ConformalInterval:
        return ConformalInterval(
            predicted=float(score),
            lower=float(score) - self.half_width,
            upper=float(score) + self.half_width,
            half_width=self.half_width,
            alpha=self.alpha,
        )


def fit(
    *,
    calibration_scores: Sequence[float],
    calibration_labels: Sequence[float],
    alpha: float = DEFAULT_ALPHA,
) -> ConformalCalibration:
    """Fit a split-conformal calibration from paired scores + labels.

    The nonconformity score is the residual magnitude ``|label − score|``
    (canonical choice for regression-style scores).
    """
    if not 0.0 < alpha < 1.0:
        raise ValueError("alpha must be in (0, 1)")

    scores = np.asarray(list(calibration_scores), dtype=float)
    labels = np.asarray(list(calibration_labels), dtype=float)
    if scores.shape != labels.shape:
        raise ValueError("calibration_scores and calibration_labels must have matching shapes")
    if scores.size == 0:
        raise ValueError("calibration set must have at least one pair")

    residuals = np.abs(labels - scores)
    n = residuals.size
    # Vovk-Gammerman-Shafer §4 — finite-sample quantile with the
    # +1 correction so the coverage guarantee holds at small n.
    quantile_level = min(1.0, math.ceil((n + 1) * (1.0 - alpha)) / n)
    half_width = float(np.quantile(residuals, quantile_level))
    return ConformalCalibration(
        alpha=alpha,
        half_width=half_width,
        calibration_set_size=n,
    )


def coverage_indicator(
    *,
    predicted: float,
    true_label: float,
    interval: ConformalInterval,
) -> bool:
    """Return True iff the true label fell inside the predicted band.

    Used by :mod:`apps.pipeline.services.adaptive_conformal_inference` to
    drive its online α update, and by operator dashboards to report
    observed coverage vs target.
    """
    return interval.lower <= true_label <= interval.upper


def observed_coverage(
    *,
    intervals: Sequence[ConformalInterval],
    true_labels: Sequence[float],
) -> float:
    """Return the fraction of labels that fell inside their intervals.

    Used for audit logs and the `meta_hpo_eval` NDCG evaluator's
    coverage sanity check.
    """
    if len(intervals) != len(true_labels):
        raise ValueError("intervals and true_labels must have equal length")
    if not intervals:
        return 0.0
    hits = sum(
        1
        for i, y in zip(intervals, true_labels)
        if coverage_indicator(predicted=i.predicted, true_label=y, interval=i)
    )
    return hits / len(intervals)
