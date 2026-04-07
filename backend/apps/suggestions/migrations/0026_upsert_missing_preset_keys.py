"""Upsert missing preset keys into the Recommended preset for existing installs.

Covers gaps found during the FR completion audit:
- FR-023: Reddit Hot Decay settings (Django side was missing)
- FR-025: Session Co-Occurrence Signal (preset migration was missing)
- FR-038: Information Gain Scoring (forward-declared, migration was missing)
- FR-039: Entity Salience Match (forward-declared, migration was missing)
- FR-047: Navigation Path Prediction (forward-declared, migration was missing)
- FR-048: Topical Authority Cluster Density (forward-declared, migration was missing)
- FR-049: Query Intent Funnel Alignment (forward-declared, migration was missing)
- FR-050: Seasonality & Temporal Demand Matching (forward-declared, migration was missing)
"""

from django.db import migrations


NEW_VALUES = {
    # Value model weight rebalance (sum was 1.15, now 1.0)
    "value_model.w_relevance": "0.35",
    "value_model.w_traffic": "0.25",
    "value_model.w_engagement": "0.08",
    "value_model.w_cooccurrence": "0.12",
    # FR-023 - Reddit Hot Decay
    "value_model.hot_decay_enabled": "true",
    "value_model.hot_gravity": "0.05",
    "value_model.hot_clicks_weight": "1.0",
    "value_model.hot_impressions_weight": "0.05",
    "value_model.hot_lookback_days": "90",
    # FR-025 - Session Co-Occurrence Signal
    "value_model.co_occurrence_signal_enabled": "true",
    "value_model.w_cooccurrence": "0.15",
    "value_model.co_occurrence_fallback_value": "0.5",
    "value_model.co_occurrence_min_co_sessions": "5",
    # FR-038 - Information Gain Scoring (forward-declared)
    "information_gain.enabled": "true",
    "information_gain.ranking_weight": "0.03",
    "information_gain.min_source_chars": "200",
    # FR-039 - Entity Salience Match (forward-declared)
    "entity_salience.enabled": "true",
    "entity_salience.ranking_weight": "0.04",
    "entity_salience.max_salient_terms": "10",
    "entity_salience.max_site_document_frequency": "20",
    "entity_salience.min_source_term_frequency": "2",
    # FR-045 - Anchor Diversity & Exact-Match Reuse Guard (forward-declared)
    "anchor_diversity.enabled": "true",
    "anchor_diversity.ranking_weight": "0.0",
    "anchor_diversity.min_history_count": "2",
    "anchor_diversity.max_exact_match_share": "0.40",
    "anchor_diversity.max_exact_match_count": "3",
    "anchor_diversity.hard_cap_enabled": "false",
    # FR-046 - Multi-Query Fan-Out for Stage 1 Retrieval (forward-declared)
    "fan_out.enabled": "true",
    "fan_out.max_sub_queries": "3",
    "fan_out.min_segment_words": "50",
    "fan_out.rrf_k": "60",
    # FR-047 - Navigation Path Prediction (forward-declared)
    "navigation_path.enabled": "true",
    "navigation_path.ranking_weight": "0.04",
    "navigation_path.lookback_days": "90",
    "navigation_path.min_sessions": "50",
    "navigation_path.min_transition_count": "5",
    "navigation_path.w_direct": "0.6",
    "navigation_path.w_shortcut": "0.4",
    # FR-048 - Topical Authority Cluster Density (forward-declared)
    "topical_cluster.enabled": "true",
    "topical_cluster.ranking_weight": "0.04",
    "topical_cluster.min_cluster_size": "5",
    "topical_cluster.min_site_pages": "20",
    "topical_cluster.max_staleness_days": "14",
    "topical_cluster.fallback_value": "0.5",
    # FR-049 - Query Intent Funnel Alignment (forward-declared)
    "intent_funnel.enabled": "true",
    "intent_funnel.ranking_weight": "0.03",
    "intent_funnel.optimal_offset": "1",
    "intent_funnel.sigma": "1.2",
    "intent_funnel.min_confidence": "0.25",
    "intent_funnel.navigational_confidence_threshold": "0.6",
    # FR-050 - Seasonality & Temporal Demand Matching (forward-declared)
    "seasonality.enabled": "true",
    "seasonality.ranking_weight": "0.03",
    "seasonality.min_history_months": "12",
    "seasonality.min_seasonal_strength": "0.3",
    "seasonality.anticipation_window_months": "3",
    "seasonality.w_current": "0.7",
    "seasonality.w_anticipation": "0.3",
    "seasonality.index_cap": "3.0",
}


def upsert_missing_preset_keys(apps, schema_editor):
    WeightPreset = apps.get_model("suggestions", "WeightPreset")

    preset, _ = WeightPreset.objects.get_or_create(
        name="Recommended",
        defaults={
            "is_system": True,
            "weights": dict(NEW_VALUES),
        },
    )

    weights = dict(preset.weights or {})
    weights.update(NEW_VALUES)
    preset.is_system = True
    preset.weights = weights
    preset.save(update_fields=["is_system", "weights", "updated_at"])


class Migration(migrations.Migration):

    dependencies = [
        ("suggestions", "0025_add_behavioral_hub_candidate_origin"),
    ]

    operations = [
        migrations.RunPython(upsert_missing_preset_keys, reverse_code=migrations.RunPython.noop),
    ]
