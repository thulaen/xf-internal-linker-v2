"""Seed FR-237..FR-250 default-on settings into the Recommended preset.

Companion to commits c66e6dd, 5f7f964, f97746d (the algorithm shippings)
and the upcoming wire-in commits. Without seeded AppSettings the runtime
``recommended_*`` helpers return their factory defaults — which works
but doesn't show operators that the keys exist on the Settings page
under "Pipeline".

Citations live in :mod:`apps.suggestions.recommended_weights` next to
the same key names. This migration only seeds; the citations are the
single source of truth in code.

Existing operator-overridden ``AppSetting`` values are NOT touched —
only the ``WeightPreset["Recommended"].weights`` JSONB seed is updated
with new keys, and ``AppSetting`` rows are created via
``get_or_create`` (which is a no-op when the key already exists).
"""

from django.db import migrations


NEW_VALUES = {
    # FR-239 — Stage-1 MMR rerank
    "pipeline.stage1_mmr_enabled": "true",
    "pipeline.stage1_overfetch_multiplier": "2",
    "pipeline.stage1_mmr_lambda": "0.7",
    # FR-240 — Hybrid retrieval (BM25 + RRF)
    "pipeline.hybrid_retrieval_enabled": "true",
    "pipeline.bm25_k1": "1.2",
    "pipeline.bm25_b": "0.75",
    "pipeline.rrf_k": "60",
    "pipeline.lexical_top_k": "50",
    # FR-247 — Fast-path observability
    "pipeline.cpp_path_alert_threshold": "0.05",
    # FR-249 — Embedding age decay
    "pipeline.embedding_age_half_life_days": "365",
    "pipeline.embedding_age_weight_in_composite": "0.05",
    # FR-245 — Calibrated thresholds
    "pipeline.calibration_enabled": "true",
    "pipeline.min_calibrated_probability": "0.5",
    "pipeline.calibration_recalibration_cadence_days": "30",
    "pipeline.calibration_validation_set_min_size": "1000",
    # FR-246 — NRT delta FAISS
    "pipeline.nrt_delta_enabled": "true",
    "pipeline.nrt_delta_refresh_seconds": "60",
    "pipeline.nrt_delta_max_size": "10000",
    "pipeline.nrt_delta_flush_threshold_size": "5000",
}


def seed_fr237_fr250_defaults(apps, schema_editor):
    WeightPreset = apps.get_model("suggestions", "WeightPreset")
    AppSetting = apps.get_model("core", "AppSetting")

    preset, _ = WeightPreset.objects.get_or_create(
        name="Recommended",
        defaults={"is_system": True, "weights": dict(NEW_VALUES)},
    )
    weights = dict(preset.weights or {})
    weights.update(NEW_VALUES)
    preset.is_system = True
    preset.weights = weights
    preset.save(update_fields=["is_system", "weights", "updated_at"])

    for key, value in NEW_VALUES.items():
        AppSetting.objects.get_or_create(
            key=key,
            defaults={"value": value},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0060_drop_orphan_feedback_bucket_key"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_fr237_fr250_defaults,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
