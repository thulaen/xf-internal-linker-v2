"""Ranker score function exposed as a pure NumPy callable — pick #47 enabler.

The production ranker (:func:`apps.pipeline.services.ranker.score_destination_matches`)
takes a long argument list and produces side-effects. Kernel SHAP needs a
**pure** ``f(features) → scores`` callable so it can sample arbitrary
feature-coalition replacements during attribution. This module builds
that pure adapter on top of the same scoring contract.

Two pieces:

1. :data:`FEATURE_COLUMNS` — the canonical, ordered list of feature
   column names + their AppSetting weight keys + display labels.
   Single source of truth shared with
   :mod:`apps.suggestions.services.suggestion_explainer` so the bar
   chart and SHAP attributions agree on column ordering.

2. :func:`build_score_fn(weights)` — returns a closure
   ``f(X: np.ndarray[batch, n_features]) → np.ndarray[batch]`` that
   computes the same linear blend the ranker uses, plus a placeholder
   for non-linear post-processors (thin-page penalty, cluster
   suppression, etc.) when they're added later. Today the ranker's
   score is linear — so the closure is too — but the contract is set
   up so a future patch can flip on non-linearities without touching
   the SHAP call site.

Background features (the SHAP "what does the model do without this
feature?" baseline) come from :func:`load_background_features` which
samples from recent ``Suggestion`` rows.
"""

from __future__ import annotations

import logging
from typing import Callable, Mapping

import numpy as np

logger = logging.getLogger(__name__)


#: Canonical ordering. Matches
#: :data:`apps.suggestions.services.suggestion_explainer.EXPLAINED_COMPONENTS`
#: byte-for-byte so the two paths stay in sync.
FEATURE_COLUMNS: tuple[tuple[str, str, str], ...] = (
    ("score_semantic", "w_semantic", "Semantic similarity"),
    ("score_keyword", "w_keyword", "Keyword overlap"),
    ("score_node_affinity", "w_node", "Node affinity"),
    ("score_quality", "w_quality", "Host quality"),
    ("score_phrase_relevance", "phrase_relevance.ranking_weight", "Phrase relevance"),
    ("score_link_freshness", "link_freshness.ranking_weight", "Link freshness"),
    ("score_field_aware_relevance", "field_aware_relevance.ranking_weight", "Field-aware relevance"),
    ("score_rare_term_propagation", "rare_term_propagation.ranking_weight", "Rare-term propagation"),
    ("score_learned_anchor_corroboration", "learned_anchor.ranking_weight", "Learned-anchor corroboration"),
    ("score_ga4_gsc", "ga4_gsc.ranking_weight", "GA4/GSC engagement"),
    ("score_click_distance", "click_distance.ranking_weight", "Click-distance prior"),
)


#: Default size of the SHAP background sample. 100 is the
#: pick-47 spec §6 default — enough variation for stable attributions
#: without blowing the on-demand 50-100 MB peak.
DEFAULT_BACKGROUND_SIZE: int = 100


def feature_field_names() -> list[str]:
    return [field_name for field_name, _, _ in FEATURE_COLUMNS]


def feature_display_names() -> list[str]:
    return [label for _, _, label in FEATURE_COLUMNS]


def feature_weight_keys() -> list[str]:
    return [weight_key for _, weight_key, _ in FEATURE_COLUMNS]


def extract_feature_vector(suggestion) -> np.ndarray:
    """Pull the feature vector from a Suggestion row in canonical order.

    Missing fields default to the neutral baseline (0.5) so the score_fn
    behaves predictably on partial-load mocks (e.g. test suites).
    """
    values: list[float] = []
    for field_name, _, _ in FEATURE_COLUMNS:
        raw = getattr(suggestion, field_name, None)
        values.append(0.5 if raw is None else float(raw))
    return np.asarray(values, dtype=np.float64)


def build_score_fn(weights: Mapping[str, float]) -> Callable[[np.ndarray], np.ndarray]:
    """Return a pure ``score_fn(X) → y`` for the current weight vector.

    The output is the same composite the ranker computes for the
    persisted ``score_final`` column:

        score = baseline + Σ_i w_i × (x_i − baseline)

    where ``baseline = 0.5`` is the project-wide neutral score
    convention. For today's linear ranker this is exact; when the
    ranker grows non-linear post-processing (thin-page penalty, cluster
    suppression), extend this closure rather than touching the SHAP
    call site so the explanation contract stays single-source.
    """
    weight_vec = np.asarray(
        [float(weights.get(key, 0.0)) for _, key, _ in FEATURE_COLUMNS],
        dtype=np.float64,
    )
    baseline = 0.5

    def score_fn(features: np.ndarray) -> np.ndarray:
        x = np.asarray(features, dtype=np.float64)
        if x.ndim == 1:
            x = x.reshape(1, -1)
        # Linear blend.
        contributions = (x - baseline) * weight_vec
        scores = baseline + contributions.sum(axis=1)
        # ── Non-linear post-processors (extension point) ──
        # When the ranker adds thin-page penalty or cluster
        # suppression to score_final, replicate them here so SHAP
        # samples the same non-linear surface the production scorer
        # produces.
        return scores

    return score_fn


def load_background_features(
    *,
    size: int = DEFAULT_BACKGROUND_SIZE,
    exclude_pk: object | None = None,
) -> np.ndarray | None:
    """Sample a background feature matrix from recent Suggestion rows.

    Returns ``None`` when the DB has fewer than 5 reviewed rows — Kernel
    SHAP with a tiny background gives high-variance attributions that
    mislead operators. The explainer falls back to direct linear
    attribution in that case (which is exact for our linear scorer
    anyway).
    """
    try:
        from apps.suggestions.models import Suggestion
    except Exception:  # pragma: no cover — Django not initialised
        return None

    qs = Suggestion.objects.all()
    if exclude_pk is not None:
        qs = qs.exclude(pk=exclude_pk)
    fields = [field_name for field_name, _, _ in FEATURE_COLUMNS]
    rows = list(
        qs.order_by("-created_at")[:size].values(*fields)
    )
    if len(rows) < 5:
        return None
    matrix = np.asarray(
        [
            [float(row.get(field) or 0.5) for field in fields]
            for row in rows
        ],
        dtype=np.float64,
    )
    return matrix
