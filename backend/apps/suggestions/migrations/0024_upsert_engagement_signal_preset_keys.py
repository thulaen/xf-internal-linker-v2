"""Upsert FR-024 engagement signal keys into the Recommended preset for existing installs."""

from django.db import migrations


NEW_VALUES = {
    # FR-024 - TikTok Read-Through Rate Engagement Signal
    "value_model.engagement_signal_enabled": "true",
    "value_model.w_engagement": "0.1",
    "value_model.engagement_lookback_days": "30",
    "value_model.engagement_words_per_minute": "200",
    "value_model.engagement_cap_ratio": "1.5",
    "value_model.engagement_fallback_value": "0.5",
}


def upsert_engagement_signal_preset_keys(apps, schema_editor):
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
        ("suggestions", "0023_add_anchor_too_long_paragraph_cluster_skip_reasons"),
    ]

    operations = [
        migrations.RunPython(
            upsert_engagement_signal_preset_keys, reverse_code=migrations.RunPython.noop
        ),
    ]
