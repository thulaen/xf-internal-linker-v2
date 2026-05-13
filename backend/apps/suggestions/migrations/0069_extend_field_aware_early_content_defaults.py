"""FR-011 early main-content field defaults.

Seeds the extra FR-011 field weights so existing installs see the new
default-on split in the Recommended preset and settings screen.
"""

from django.db import migrations


FIELD_AWARE_VALUES = {
    "field_aware_relevance.ranking_weight": (
        "0.10",
        "Field-aware relevance ranking weight",
    ),
    "field_aware_relevance.title_field_weight": (
        "0.30",
        "Field-aware title field weight",
    ),
    "field_aware_relevance.heading_field_weight": (
        "0.15",
        "Field-aware heading field weight",
    ),
    "field_aware_relevance.intro_field_weight": (
        "0.20",
        "Field-aware intro field weight",
    ),
    "field_aware_relevance.body_field_weight": (
        "0.15",
        "Field-aware body field weight",
    ),
    "field_aware_relevance.scope_field_weight": (
        "0.10",
        "Field-aware scope field weight",
    ),
    "field_aware_relevance.learned_anchor_field_weight": (
        "0.10",
        "Field-aware learned-anchor field weight",
    ),
}


def seed_field_aware_early_content_defaults(apps, schema_editor):
    WeightPreset = apps.get_model("suggestions", "WeightPreset")
    AppSetting = apps.get_model("core", "AppSetting")

    preset, _ = WeightPreset.objects.get_or_create(
        name="Recommended",
        defaults={
            "is_system": True,
            "weights": {
                key: value for key, (value, _description) in FIELD_AWARE_VALUES.items()
            },
        },
    )
    weights = dict(preset.weights or {})
    weights.update(
        {key: value for key, (value, _description) in FIELD_AWARE_VALUES.items()}
    )
    preset.is_system = True
    preset.weights = weights
    preset.save(update_fields=["is_system", "weights", "updated_at"])

    for key, (value, description) in FIELD_AWARE_VALUES.items():
        AppSetting.objects.get_or_create(
            key=key,
            defaults={
                "value": value,
                "value_type": "float",
                "category": "ml",
                "description": description,
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0068_suggestion_unique_5tuple"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_field_aware_early_content_defaults,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
