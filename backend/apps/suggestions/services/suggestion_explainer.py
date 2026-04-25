"""Per-suggestion explanation service — pick #47 Kernel SHAP wiring.

Two explanation methods, picked at runtime:

1. **Kernel SHAP** (Lundberg & Lee 2017) — the real deal. Samples
   feature coalitions through a pure ranker score function
   (:func:`apps.pipeline.services.ranker_score_fn.build_score_fn`) and
   returns the same Shapley values that would come out of any
   off-the-shelf SHAP implementation. Required when the ranker grows
   non-linear post-processors (thin-page penalty, cluster
   suppression, RRF fusion); for the current linear scorer the values
   match direct linear attribution within sampling noise.

2. **Linear attribution fallback** — direct ``contribution =
   weight × (value − baseline)`` per component. Mathematically exact
   for the current linear scorer; used when:

   - the ``shap`` library is unavailable in the runtime,
   - the DB has < 5 reviewed Suggestions to build a stable Kernel SHAP
     background,
   - the Kernel SHAP call itself raises (numerical hiccup, OOM under
     contention, etc.).

The output shape (:class:`Explanation` + :class:`FeatureContribution`)
is identical between the two methods so the W4 Angular panel doesn't
need to know which one ran. The ``method`` field tells operators
whether they're seeing real SHAP or the fallback ("kernel_shap" vs
"linear_attribution").
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

# Import the module rather than its symbols so unit-test patches via
# ``patch.object(ranker_score_fn, "load_background_features", ...)``
# intercept calls from this module too.
from apps.pipeline.services import ranker_score_fn
from apps.pipeline.services.ranker_score_fn import (
    DEFAULT_BACKGROUND_SIZE,
    FEATURE_COLUMNS,
)

logger = logging.getLogger(__name__)


#: Backwards-compatible alias. Earlier W4 callers imported
#: ``EXPLAINED_COMPONENTS`` from this module; the canonical home is
#: now :data:`ranker_score_fn.FEATURE_COLUMNS` so the SHAP path and
#: the linear-fallback path agree on column ordering.
EXPLAINED_COMPONENTS = FEATURE_COLUMNS


#: Number of Optuna-style coalition samples Kernel SHAP evaluates per
#: explanation. Pick #47 spec §6 default — fits the < 1 s response
#: budget and gives stable attributions on 11 features.
DEFAULT_NSAMPLES: int = 200


@dataclass(frozen=True)
class FeatureContribution:
    """One feature's contribution to the explained suggestion's score."""

    feature_name: str
    value: float
    shap_value: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class Explanation:
    """Full per-suggestion explanation.

    Same shape as :class:`apps.pipeline.services.shap_explainer.Explanation`
    so the W4 endpoint and Angular panel are method-agnostic.
    """

    predicted_value: float
    baseline: float
    contributions: list[FeatureContribution]
    method: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "predicted_value": self.predicted_value,
            "baseline": self.baseline,
            "method": self.method,
            "contributions": [c.to_dict() for c in self.contributions],
        }


def explain_suggestion(suggestion) -> Explanation:
    """Return per-feature attributions for a single Suggestion.

    Tries Kernel SHAP first; falls back to direct linear attribution
    when SHAP isn't available or the DB lacks enough background. Both
    paths produce :class:`Explanation` with identical shape — the
    ``method`` field tells operators which one ran.
    """
    weights = _load_weights()
    shap_explanation = _try_kernel_shap(suggestion, weights=weights)
    if shap_explanation is not None:
        return shap_explanation
    return _linear_attribution(suggestion, weights=weights)


# ── Kernel SHAP path ──────────────────────────────────────────────


def _try_kernel_shap(suggestion, *, weights: dict[str, float]) -> Explanation | None:
    """Run Kernel SHAP through the pure ranker score_fn.

    Returns ``None`` on any failure so the caller falls through to the
    linear-attribution path. Failures are intentionally absorbed (just
    logged at DEBUG) — the Explain endpoint never raises because of an
    explainability hiccup.
    """
    try:
        # Local import keeps the module importable in environments
        # without ``shap`` (test harnesses, minimal containers).
        from apps.pipeline.services.shap_explainer import (
            HAS_SHAP,
            SHAPUnavailable,
            explain as kernel_shap_explain,
        )
    except Exception:
        logger.debug("shap helper unavailable — using linear attribution")
        return None

    if not HAS_SHAP:
        return None

    try:
        background = ranker_score_fn.load_background_features(
            size=DEFAULT_BACKGROUND_SIZE,
            exclude_pk=getattr(suggestion, "pk", None),
        )
    except Exception:
        logger.debug(
            "Kernel SHAP background load failed — using linear attribution",
            exc_info=True,
        )
        return None

    if background is None or background.shape[0] < 5:
        # Too little history for a stable SHAP fit — the linear
        # fallback gives exact answers for the current model anyway.
        return None

    subject = ranker_score_fn.extract_feature_vector(suggestion)
    score_fn = ranker_score_fn.build_score_fn(weights)

    try:
        result = kernel_shap_explain(
            score_fn=score_fn,
            subject=subject,
            background=background,
            feature_names=ranker_score_fn.feature_display_names(),
            nsamples=DEFAULT_NSAMPLES,
        )
    except SHAPUnavailable:
        return None
    except Exception:
        logger.debug(
            "Kernel SHAP raised — using linear attribution", exc_info=True
        )
        return None

    contributions = [
        FeatureContribution(
            feature_name=row.feature_name,
            value=row.value,
            shap_value=row.shap_value,
        )
        for row in result.contributions
    ]
    return Explanation(
        predicted_value=result.predicted_value,
        baseline=result.baseline,
        contributions=contributions,
        method="kernel_shap",
    )


# ── Linear-attribution fallback ───────────────────────────────────


def _linear_attribution(suggestion, *, weights: dict[str, float]) -> Explanation:
    """Direct ``contribution = weight × (value − baseline)`` per component.

    Exact for the current linear ranker. Used when Kernel SHAP can't
    run (no shap dep, cold-start DB, transient SHAP error).
    """
    contributions: list[FeatureContribution] = []
    total = 0.0
    baseline = 0.5
    for field_name, weight_key, label in EXPLAINED_COMPONENTS:
        raw = getattr(suggestion, field_name, None)
        if raw is None:
            continue
        value = float(raw)
        weight = float(weights.get(weight_key, 0.0))
        if weight == 0.0:
            contributions.append(
                FeatureContribution(
                    feature_name=label,
                    value=value,
                    shap_value=0.0,
                )
            )
            continue
        contribution = weight * (value - baseline)
        total += contribution
        contributions.append(
            FeatureContribution(
                feature_name=label,
                value=value,
                shap_value=contribution,
            )
        )
    contributions.sort(key=lambda c: -abs(c.shap_value))
    return Explanation(
        predicted_value=baseline + total,
        baseline=baseline,
        contributions=contributions,
        method="linear_attribution",
    )


def _load_weights() -> dict[str, float]:
    """Load ranker weights from AppSetting.

    Falls back to an empty dict on any failure — the explanation still
    renders, just with all "weight=0" rows so operators see the
    component list without a crash.
    """
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return {}

    keys = [w_key for _, w_key, _ in EXPLAINED_COMPONENTS]
    rows = AppSetting.objects.filter(key__in=keys).values_list("key", "value")
    weights: dict[str, float] = {}
    for key, value in rows:
        try:
            weights[key] = float(value)
        except (TypeError, ValueError):
            continue
    return weights
