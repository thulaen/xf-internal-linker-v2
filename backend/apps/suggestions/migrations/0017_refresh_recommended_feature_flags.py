"""Refresh the Recommended preset so all shipped ranking features start enabled."""

from django.db import migrations


SETTING_ROWS = (
    (
        "silo.mode",
        "disabled",
        "prefer_same_silo",
        "str",
        "Topical silo enforcement mode.",
    ),
    (
        "ga4_gsc.ranking_weight",
        "0.00",
        "0.05",
        "float",
        "Ranking weight for the GA4/GSC content-value signal.",
    ),
    (
        "explore_exploit.enabled",
        "false",
        "true",
        "bool",
        "Whether feedback-driven explore/exploit reranking is active.",
    ),
    (
        "explore_exploit.ranking_weight",
        "0.10",
        "0.08",
        "float",
        "Multiplier weight for the feedback-driven score component.",
    ),
    (
        "explore_exploit.exploration_rate",
        "1.0",
        "1.41421356237",
        "float",
        "UCB1 exploration-rate constant adapted to this implementation.",
    ),
)

OLD_VALUES = {key: old_value for key, old_value, *_ in SETTING_ROWS}
NEW_VALUES = {key: new_value for key, _old, new_value, *_ in SETTING_ROWS}
SETTING_META = {
    key: {"value_type": value_type, "category": "ml", "description": description}
    for key, _old, _new, value_type, description in SETTING_ROWS
}


def refresh_recommended_preset(apps, schema_editor):
    WeightPreset = apps.get_model("suggestions", "WeightPreset")
    AppSetting = apps.get_model("core", "AppSetting")

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

    for key, new_value in NEW_VALUES.items():
        meta = SETTING_META[key]
        setting = AppSetting.objects.filter(key=key).first()
        if setting is None or setting.value == OLD_VALUES[key]:
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": new_value,
                    "value_type": meta["value_type"],
                    "category": meta["category"],
                    "description": meta["description"],
                    "is_secret": False,
                },
            )


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0016_seed_recommended_preset"),
        ("core", "0003_alter_appsetting_category"),
    ]

    operations = [
        migrations.RunPython(
            refresh_recommended_preset, reverse_code=migrations.RunPython.noop
        ),
    ]
