"""FR-249 + FR-018 — seed `w_embedding_age` as the 5th L-BFGS tunable.

`apps.suggestions.services.weight_tuner.WeightTuner.__init__` now
appends `score_embedding_age` to its feature_keys when
`pipeline.embedding_age_weight_in_composite` is positive (default).
This migration seeds the matching `w_embedding_age = 0.05` weight
into the Recommended preset and live AppSetting so the tuner has a
non-zero starting point for the L-BFGS-B optimisation.

Citations live in `recommended_weights.py` next to the same key.
Idempotent via `get_or_create`.
"""

from django.db import migrations


NEW_VALUES = {
    "w_embedding_age": "0.05",
}


def seed_w_embedding_age(apps, schema_editor):
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
        ("suggestions", "0063_add_score_embedding_age"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(
            seed_w_embedding_age,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
