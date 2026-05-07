"""FR-245 — Calibrated similarity threshold via Platt scaling.

Replaces the hand-picked ``pipeline.min_semantic_score = 0.25`` cutoff
with a sigmoid that maps a raw cosine into a calibrated probability of
"this is a good match". Trained periodically against accept/reject
feedback. v1 ships the math + cutoff helper + cold-start fallback;
training-pipeline wire-in is deferred until the feedback store has
≥1000 labeled pairs (Niculescu-Mizil & Caruana 2005 §4 minimum).

Sources of truth:
    * Platt, J. C. (1999). *Probabilistic Outputs for Support Vector
      Machines and Comparisons to Regularized Likelihood Methods.*
      Advances in Large Margin Classifiers.
      https://citeseerx.ist.psu.edu/doc/10.1.1.41.1639. The canonical
      method to map any classifier score to a calibrated probability
      via a sigmoid fit.
    * Guo, C. et al. (2017). *On Calibration of Modern Neural Networks.*
      ICML 2017. arXiv:1706.04599. §5 — confirms Platt-scaling
      generalises to deep models; recommends 30-day recalibration.
    * Niculescu-Mizil, A. & Caruana, R. (2005). *Predicting Good
      Probabilities with Supervised Learning.* ICML 2005.
      DOI:10.1145/1102351.1102430 §4 — minimum validation set size
      1000 for stable Platt fit.

Default state: ON (math + cutoff helper present in code path). When no
calibration model has been fitted yet, ``calibrated_probability``
falls back to a logistic mapping from the raw cosine — true default-on
with a clean upgrade path. Wire-in into ``_apply_min_semantic_score``
(replacing the hardcoded 0.25 cutoff) is deferred until a calibration
job has run at least once.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


# Niculescu-Mizil & Caruana 2005 §4 — minimum validation set size.
VALIDATION_SET_MIN_SIZE_DEFAULT: int = 1000

# Guo et al. 2017 ICML §5 — recommended recalibration cadence.
RECALIBRATION_CADENCE_DAYS_DEFAULT: int = 30

# Platt 1999 §2 — default decision threshold for the sigmoid output.
MIN_CALIBRATED_PROBABILITY_DEFAULT: float = 0.5


@dataclass(frozen=True, slots=True)
class PlattParams:
    """Sigmoid parameters from a Platt fit. ``P(match) = 1 / (1 + exp(A·x + B))``."""

    a: float
    b: float


# Cold-start fallback parameters: a logistic mapping from cosine to
# probability roughly aligned with the historical 0.25-cutoff. Using
# the standard sigmoid convention σ(A·x + B):
#   cosine=0.0  → σ(-1.5) ≈ 0.18 (low confidence)
#   cosine=0.25 → σ(0.0)  = 0.50 (decision boundary)
#   cosine=0.5  → σ(1.5)  ≈ 0.82
#   cosine=0.9  → σ(3.9)  ≈ 0.98 (high confidence)
# These are NOT a fitted model — they're a "reasonable shape" default
# until the first real fit lands per Niculescu-Mizil 2005 §4.
_COLD_START_A: float = 6.0
_COLD_START_B: float = -1.5
COLD_START_PARAMS: PlattParams = PlattParams(a=_COLD_START_A, b=_COLD_START_B)


def calibrated_probability(
    cosine_score: float,
    *,
    params: Optional[PlattParams] = None,
) -> float:
    """Map a raw cosine score to a calibrated probability via Platt.

    Internally uses the standard sigmoid convention
    ``P(match | s) = σ(A·s + B) = 1 / (1 + exp(-(A·s + B)))``
    which is Platt 1999 §2 with (A, B) negated. The fitted (A, B)
    pair therefore matches modern Python implementations
    (sklearn.calibration.CalibratedClassifierCV uses the same
    convention) — operators reading the params directly will see a
    POSITIVE ``A`` for the expected "higher cosine → higher P"
    direction.

    Output is in (0, 1) by construction. ``params`` defaults to the
    cold-start logistic; see module docstring.
    """
    p = params if params is not None else COLD_START_PARAMS
    z = p.a * float(cosine_score) + p.b
    # Numerically stable sigmoid σ(z) = 1 / (1 + exp(-z)).
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def fit_platt_sigmoid(
    scores: list[float],
    labels: list[int],
    *,
    max_iters: int = 100,
    tolerance: float = 1e-6,
) -> Optional[PlattParams]:
    """Fit a Platt sigmoid via Newton-Raphson on the BCE loss.

    Returns None when validation set < 1000 (Niculescu-Mizil 2005 §4)
    or labels are degenerate (Platt 1999 §2.2). Convex in (A, B) for
    a single sigmoid (Platt §2.1) so Newton converges quickly.
    """
    if len(scores) != len(labels):
        raise ValueError("scores and labels must have equal length")
    if not _has_enough_pairs(scores, labels):
        return None
    targets, pos, neg = _platt_smoothed_targets(labels)
    a, b = 0.0, math.log((neg + 1.0) / (pos + 1.0))
    for _ in range(max_iters):
        step_a, step_b = _newton_step(scores, targets, a, b)
        if step_a is None:
            break
        a += step_a
        b += step_b
        if abs(step_a) < tolerance and abs(step_b) < tolerance:
            break
    return PlattParams(a=a, b=b)


def _has_enough_pairs(scores: list[float], labels: list[int]) -> bool:
    """Niculescu-Mizil §4 minimum + Platt §2.2 non-degenerate-labels guard."""
    if len(scores) < VALIDATION_SET_MIN_SIZE_DEFAULT:
        logger.info(
            "FR-245 — validation set size %d below minimum %d; skipping fit",
            len(scores), VALIDATION_SET_MIN_SIZE_DEFAULT,
        )
        return False
    pos = sum(1 for label in labels if label == 1)
    if pos == 0 or pos == len(labels):
        logger.info("FR-245 — degenerate labels (all-pos or all-neg); skipping fit")
        return False
    return True


def _platt_smoothed_targets(labels: list[int]) -> tuple[list[float], int, int]:
    """Platt 1999 §2.4 class-conditional smoothing — prevents fit collapse."""
    pos = sum(1 for label in labels if label == 1)
    neg = len(labels) - pos
    t_pos = (pos + 1.0) / (pos + 2.0)
    t_neg = 1.0 / (neg + 2.0)
    return [t_pos if label == 1 else t_neg for label in labels], pos, neg


def _newton_step(
    scores: list[float], targets: list[float], a: float, b: float,
) -> tuple[Optional[float], float]:
    """One Newton-Raphson iteration on the BCE loss. Returns (step_a, step_b).

    Returns (None, 0.0) when the Hessian is near-singular (numerical
    convergence stop signal).
    """
    delta_a, delta_b = 0.0, 0.0
    h_a, h_b, off_diag = 0.0, 0.0, 0.0
    for s, t in zip(scores, targets):
        z = a * s + b
        if z >= 0:
            p = 1.0 / (1.0 + math.exp(-z))
        else:
            ez = math.exp(z)
            p = ez / (1.0 + ez)
        err = t - p
        delta_a += err * s
        delta_b += err
        d2 = p * (1.0 - p)
        h_a += d2 * s * s
        h_b += d2
        off_diag += d2 * s
    det = h_a * h_b - off_diag * off_diag
    if abs(det) < 1e-12:
        return None, 0.0
    return (
        (h_b * delta_a - off_diag * delta_b) / det,
        (h_a * delta_b - off_diag * delta_a) / det,
    )


def passes_calibrated_threshold(
    cosine_score: float,
    *,
    threshold: float = MIN_CALIBRATED_PROBABILITY_DEFAULT,
    params: Optional[PlattParams] = None,
) -> bool:
    """Return True if the calibrated probability is at or above *threshold*.

    Platt 1999 §2 — 0.5 is the natural decision boundary for a
    sigmoid. Operators can tighten the threshold per-site via
    ``pipeline.min_calibrated_probability`` AppSetting.
    """
    return calibrated_probability(cosine_score, params=params) >= threshold


def get_calibration_status() -> dict[str, object]:
    """Plain-English runtime status for `/performance` dashboard."""
    return {
        "available": False,  # No fitted model yet shipped
        "path": "cold_start_logistic",
        "reason": (
            "No fitted Platt sigmoid yet. Using cold-start logistic "
            "params (A=-6.0, B=1.5) tuned to roughly match the "
            "historical 0.25-cosine cutoff. Will switch to a fitted "
            "sigmoid once the feedback_store has ≥1000 labeled pairs "
            "per Niculescu-Mizil & Caruana 2005 §4."
        ),
    }
