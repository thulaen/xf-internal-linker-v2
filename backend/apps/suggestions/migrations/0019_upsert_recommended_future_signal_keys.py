"""Upsert FR-040 through FR-044 keys into the Recommended preset for existing installs."""

from django.db import migrations


NEW_VALUES = {
    # FR-040 - Multimedia Boost
    "multimedia_signal_enabled": "true",
    "w_multimedia": "0.10",
    "multimedia_fallback_value": "0.5",
    # FR-041 - Originality Provenance Scoring
    "originality_provenance.enabled": "true",
    "originality_provenance.ranking_weight": "0.03",
    "originality_provenance.resemblance_threshold": "0.55",
    "originality_provenance.containment_threshold": "0.80",
    # FR-042 - Fact Density Scoring
    "fact_density.enabled": "true",
    "fact_density.ranking_weight": "0.04",
    "fact_density.min_word_count": "120",
    "fact_density.density_cap_per_100_words": "8.0",
    "fact_density.filler_penalty_weight": "0.35",
    # FR-043 - Semantic Drift Penalty
    "semantic_drift.enabled": "true",
    "semantic_drift.ranking_weight": "0.03",
    "semantic_drift.tokens_per_sequence": "20",
    "semantic_drift.block_size_in_sequences": "6",
    "semantic_drift.anchor_similarity_threshold": "0.18",
    "semantic_drift.min_word_count": "180",
    # FR-044 - Internal Search Intensity Signal
    "internal_search.enabled": "true",
    "internal_search.ranking_weight": "0.02",
    "internal_search.recent_days": "3",
    "internal_search.baseline_days": "28",
    "internal_search.max_active_queries": "200",
    "internal_search.min_recent_count": "3",
}


def upsert_recommended_future_signal_keys(apps, schema_editor):
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
        ("suggestions", "0018_alter_weightadjustmenthistory_reason"),
    ]

    operations = [
        migrations.RunPython(upsert_recommended_future_signal_keys, reverse_code=migrations.RunPython.noop),
    ]
