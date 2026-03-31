"""
Weight preset service helpers shared by views, tasks, and migrations.

The preset registry is the single source of truth for which AppSetting keys
belong to a weight preset.
"""

from __future__ import annotations

from django.db import transaction

from .recommended_weights import RECOMMENDED_PRESET_WEIGHTS

# Every AppSetting key whose category is ml, link_freshness, or anchor.
# Values are stored as strings because AppSetting.value is text.
PRESET_DEFAULTS: dict[str, str] = dict(RECOMMENDED_PRESET_WEIGHTS)

# Metadata for each key (value_type + category) used when writing to AppSetting.
# Any key not listed here falls back to value_type="str", category="ml".
_KEY_META: dict[str, dict[str, str]] = {
    "w_semantic": {"value_type": "float", "category": "ml"},
    "w_keyword": {"value_type": "float", "category": "ml"},
    "w_node": {"value_type": "float", "category": "ml"},
    "w_quality": {"value_type": "float", "category": "ml"},
    "silo.mode": {"value_type": "str", "category": "ml"},
    "silo.same_silo_boost": {"value_type": "float", "category": "ml"},
    "silo.cross_silo_penalty": {"value_type": "float", "category": "ml"},
    "weighted_authority.ranking_weight": {"value_type": "float", "category": "ml"},
    "weighted_authority.position_bias": {"value_type": "float", "category": "ml"},
    "weighted_authority.empty_anchor_factor": {"value_type": "float", "category": "ml"},
    "weighted_authority.bare_url_factor": {"value_type": "float", "category": "ml"},
    "weighted_authority.weak_context_factor": {"value_type": "float", "category": "ml"},
    "weighted_authority.isolated_context_factor": {"value_type": "float", "category": "ml"},
    "rare_term_propagation.enabled": {"value_type": "bool", "category": "ml"},
    "rare_term_propagation.ranking_weight": {"value_type": "float", "category": "ml"},
    "rare_term_propagation.max_document_frequency": {"value_type": "int", "category": "ml"},
    "rare_term_propagation.minimum_supporting_related_pages": {"value_type": "int", "category": "ml"},
    "field_aware_relevance.ranking_weight": {"value_type": "float", "category": "ml"},
    "field_aware_relevance.title_field_weight": {"value_type": "float", "category": "ml"},
    "field_aware_relevance.body_field_weight": {"value_type": "float", "category": "ml"},
    "field_aware_relevance.scope_field_weight": {"value_type": "float", "category": "ml"},
    "field_aware_relevance.learned_anchor_field_weight": {"value_type": "float", "category": "ml"},
    "ga4_gsc.ranking_weight": {"value_type": "float", "category": "ml"},
    "click_distance.ranking_weight": {"value_type": "float", "category": "ml"},
    "click_distance.k_cd": {"value_type": "float", "category": "ml"},
    "click_distance.b_cd": {"value_type": "float", "category": "ml"},
    "click_distance.b_ud": {"value_type": "float", "category": "ml"},
    "explore_exploit.enabled": {"value_type": "bool", "category": "ml"},
    "explore_exploit.ranking_weight": {"value_type": "float", "category": "ml"},
    "explore_exploit.exploration_rate": {"value_type": "float", "category": "ml"},
    "clustering.enabled": {"value_type": "bool", "category": "ml"},
    "clustering.similarity_threshold": {"value_type": "float", "category": "ml"},
    "clustering.suppression_penalty": {"value_type": "float", "category": "ml"},
    "slate_diversity.enabled": {"value_type": "bool", "category": "ml"},
    "slate_diversity.diversity_lambda": {"value_type": "float", "category": "ml"},
    "slate_diversity.score_window": {"value_type": "float", "category": "ml"},
    "slate_diversity.similarity_cap": {"value_type": "float", "category": "ml"},
    "link_freshness.ranking_weight": {"value_type": "float", "category": "link_freshness"},
    "link_freshness.recent_window_days": {"value_type": "int", "category": "link_freshness"},
    "link_freshness.newest_peer_percent": {"value_type": "float", "category": "link_freshness"},
    "link_freshness.min_peer_count": {"value_type": "int", "category": "link_freshness"},
    "link_freshness.w_recent": {"value_type": "float", "category": "link_freshness"},
    "link_freshness.w_growth": {"value_type": "float", "category": "link_freshness"},
    "link_freshness.w_cohort": {"value_type": "float", "category": "link_freshness"},
    "link_freshness.w_loss": {"value_type": "float", "category": "link_freshness"},
    "phrase_matching.ranking_weight": {"value_type": "float", "category": "anchor"},
    "phrase_matching.enable_anchor_expansion": {"value_type": "bool", "category": "anchor"},
    "phrase_matching.enable_partial_matching": {"value_type": "bool", "category": "anchor"},
    "phrase_matching.context_window_tokens": {"value_type": "int", "category": "anchor"},
    "learned_anchor.ranking_weight": {"value_type": "float", "category": "anchor"},
    "learned_anchor.minimum_anchor_sources": {"value_type": "int", "category": "anchor"},
    "learned_anchor.minimum_family_support_share": {"value_type": "float", "category": "anchor"},
    "learned_anchor.enable_noise_filter": {"value_type": "bool", "category": "anchor"},
}


def get_current_weights() -> dict[str, str]:
    """Return the current value of every in-scope AppSetting key as strings."""
    from apps.core.models import AppSetting

    qs = AppSetting.objects.filter(key__in=list(PRESET_DEFAULTS)).values_list("key", "value")
    stored = dict(qs)
    return {key: stored.get(key, default) for key, default in PRESET_DEFAULTS.items()}


def compute_delta(previous: dict[str, str], new: dict[str, str]) -> dict[str, dict]:
    """Return only the keys that differ, with previous/new values."""
    delta: dict[str, dict] = {}
    all_keys = set(previous) | set(new)
    for key in all_keys:
        prev_val = previous.get(key)
        new_val = new.get(key)
        if prev_val != new_val:
            delta[key] = {"previous": prev_val, "new": new_val}
    return delta


@transaction.atomic
def apply_weights(weights: dict[str, str]) -> None:
    """Write every key from *weights* to AppSetting, falling back to defaults."""
    from apps.core.models import AppSetting

    for key, default_value in PRESET_DEFAULTS.items():
        value = str(weights.get(key, default_value))
        meta = _KEY_META.get(key, {"value_type": "str", "category": "ml"})
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "value_type": meta["value_type"],
                "category": meta["category"],
                "is_secret": False,
            },
        )


def write_history(
    *,
    source: str,
    previous_weights: dict[str, str],
    new_weights: dict[str, str],
    reason: str,
    preset=None,
    r_run_id: str = "",
) -> None:
    """Write one WeightAdjustmentHistory row after weights are applied."""
    from apps.suggestions.models import WeightAdjustmentHistory

    WeightAdjustmentHistory.objects.create(
        source=source,
        preset=preset,
        previous_weights=previous_weights,
        new_weights=new_weights,
        delta=compute_delta(previous_weights, new_weights),
        reason=reason,
        r_run_id=r_run_id,
    )
