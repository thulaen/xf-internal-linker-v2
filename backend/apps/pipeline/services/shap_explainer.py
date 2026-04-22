"""Kernel SHAP explainability — Lundberg & Lee (NeurIPS 2017).

Reference
---------
Lundberg, S. M. & Lee, S.-I. (2017). "A unified approach to
interpreting model predictions." *Advances in Neural Information
Processing Systems 30*, pp. 4765-4774.

Goal
----
Answer the question "**why did the ranker give this suggestion a
score of 0.82?**" — on demand, from the operator's Explain button.
Kernel SHAP decomposes the score into per-feature contributions::

    score(x) = baseline + Σ_f  phi_f

``phi_f`` is the Shapley value of feature ``f`` — its averaged
marginal contribution across all orderings of the feature set.
Summed across features, the SHAP values plus the baseline exactly
equal the model's prediction (that's the "additive" in SHAP).

Usage model
-----------
- Scheduled: **never**. Kernel SHAP is O(samples × features) per
  call and easily 50-100 MB peak RAM; running it on every
  suggestion would dwarf the ranker itself.
- On-demand: fires when the operator clicks Explain. The helper
  takes a ``score_fn``, a feature-vector dataclass for the subject
  suggestion, and a "background" sample of typical suggestions
  (used as the SHAP baseline). Returns a dataclass with per-feature
  contributions and the implied baseline — already sorted so the
  UI can render "these features drove the score up / down."

Why wrap ``shap`` instead of calling it directly?
  - Centralise the feature-order / display-label choice so different
    callers (suggestions explainer, import-decision explainer,
    anti-spam explainer) present SHAP values consistently.
  - Gate the import behind a guard — ``shap`` is heavy and the
    helper must stay importable even if the library is missing
    (container without the dep, for instance). The try/except shim
    mirrors what :mod:`apps.sources.product_quantization` does for
    FAISS.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Iterable, Sequence

import numpy as np

try:
    import shap

    HAS_SHAP = True
except ImportError:  # pragma: no cover — container without the dep.
    shap = None  # type: ignore[assignment]
    HAS_SHAP = False


#: Default number of coalition samples Kernel SHAP evaluates. The
#: paper's recommendation is ``2 * M + 2048`` where M is the number
#: of features; 200 is a reasonable default for the linker's typical
#: 10-30 feature vectors (well above the paper's minimum for
#: convergence) and stays inside the operator's ~second response-time
#: budget.
DEFAULT_NSAMPLES: int = 200


@dataclass(frozen=True)
class FeatureContribution:
    """One feature's contribution to the explained prediction."""

    feature_name: str
    value: float              # the raw feature value on the subject instance
    shap_value: float         # signed contribution (+ / - direction)


@dataclass(frozen=True)
class Explanation:
    """Full SHAP explanation of a single prediction."""

    predicted_value: float
    baseline: float
    contributions: list[FeatureContribution]  # sorted |shap_value| desc


class SHAPUnavailable(RuntimeError):
    """Raised when :mod:`shap` is not installed.

    Distinct from ``ImportError`` so callers wrapping the explainer
    in a feature-flag can tell "library missing, fall back to a
    simpler explanation" from "somebody's code broke".
    """


def explain(
    *,
    score_fn: Callable[[np.ndarray], np.ndarray],
    subject: Sequence[float],
    background: Iterable[Sequence[float]],
    feature_names: Sequence[str],
    nsamples: int = DEFAULT_NSAMPLES,
) -> Explanation:
    """Return per-feature SHAP contributions for a single *subject* row.

    Parameters
    ----------
    score_fn
        The model under explanation. Must accept a 2-D NumPy array of
        shape ``(batch, n_features)`` and return a 1-D array of
        predictions (length ``batch``). SHAP will call this many times.
    subject
        The specific row we want to explain, in the same feature
        order as *feature_names*.
    background
        A small representative sample of feature vectors used as
        the SHAP baseline. Kernel SHAP interprets "turning a feature
        off" as replacing it with the background value, so use
        ~100 typical suggestions for a stable baseline.
    feature_names
        Human-readable labels (``["bm25", "pagerank", …]``). Order
        must match both *subject* and *background*.
    nsamples
        Number of coalition samples Kernel SHAP evaluates.

    Raises
    ------
    SHAPUnavailable
        If the ``shap`` library is not installed.
    ValueError
        On shape or length mismatches.
    """
    if not HAS_SHAP or shap is None:
        raise SHAPUnavailable(
            "shap library is not installed — `pip install shap` "
            "or remove the call site. See requirements.txt for "
            "the pinned version."
        )

    subject_arr = np.asarray(subject, dtype=float).reshape(1, -1)
    background_arr = np.asarray(list(background), dtype=float)
    if background_arr.ndim != 2:
        raise ValueError("background must be a 2-D array of feature rows")
    if subject_arr.shape[1] != background_arr.shape[1]:
        raise ValueError("subject and background must share feature count")
    if subject_arr.shape[1] != len(feature_names):
        raise ValueError("feature_names length must match feature count")
    if background_arr.shape[0] == 0:
        raise ValueError("background must have at least one row")
    if nsamples <= 0:
        raise ValueError("nsamples must be > 0")

    explainer = shap.KernelExplainer(score_fn, background_arr, silent=True)
    shap_values = explainer.shap_values(subject_arr, nsamples=nsamples)

    # ``shap`` returns different shapes for single vs multi-output
    # models; the linker's ranker is single-output, so unwrap.
    if isinstance(shap_values, list):
        shap_values = shap_values[0]
    shap_values = np.asarray(shap_values).reshape(-1)

    baseline = float(np.asarray(explainer.expected_value).reshape(-1)[0])
    predicted = baseline + float(shap_values.sum())

    contributions = [
        FeatureContribution(
            feature_name=str(name),
            value=float(subject_arr[0, idx]),
            shap_value=float(shap_values[idx]),
        )
        for idx, name in enumerate(feature_names)
    ]
    contributions.sort(key=lambda c: -abs(c.shap_value))

    return Explanation(
        predicted_value=predicted,
        baseline=baseline,
        contributions=contributions,
    )


def top_contributions(
    explanation: Explanation,
    *,
    n: int = 5,
) -> list[FeatureContribution]:
    """Return the top-*n* contributions by absolute SHAP magnitude.

    Convenience for UI rendering — the Explain panel typically
    surfaces 5 features, not the whole vector.
    """
    if n < 0:
        raise ValueError("n must be >= 0")
    return list(explanation.contributions[:n])
