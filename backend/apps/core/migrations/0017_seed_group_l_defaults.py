from django.db import migrations


DEFAULTS = {
    "system.startup_smoke_test_enabled": {
        "value": "true",
        "value_type": "bool",
        "category": "general",
        "description": "Run startup checks for artifact-table duplicate and retention discipline.",
    },
    "system.audit_log_enabled": {
        "value": "true",
        "value_type": "bool",
        "category": "general",
        "description": "Write unified audit events for operator-visible state changes.",
    },
    "feature_flags.enabled": {
        "value": "true",
        "value_type": "bool",
        "category": "general",
        "description": "Enable feature-flag evaluation and exposure logging.",
    },
}


DECLARED_FLAGS = (
    (
        "operations-feed",
        "Show the live Operations Feed narration surface.",
    ),
    (
        "suggestion-readiness-gate",
        "Block Review until prerequisite data is ready.",
    ),
    (
        "meta-algorithms-expanded-registry",
        "Show active and spec-only meta algorithms in Settings.",
    ),
)


def seed_defaults(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    WeightPreset = apps.get_model("suggestions", "WeightPreset")
    FeatureFlag = apps.get_model("audit", "FeatureFlag")

    # 2026-05-09: switched from ``update_or_create`` to ``get_or_create`` so
    # re-running this migration (fresh test DB, database restore, etc.) no
    # longer trampling any operator override. Matches DEFAULT-ON-RULE.md.
    for key, meta in DEFAULTS.items():
        AppSetting.objects.get_or_create(key=key, defaults=meta)

    preset, _ = WeightPreset.objects.get_or_create(
        name="Recommended",
        defaults={"is_system": True, "weights": {}},
    )
    weights = dict(preset.weights or {})
    for key, meta in DEFAULTS.items():
        weights[key] = meta["value"]
    preset.is_system = True
    preset.weights = weights
    preset.save(update_fields=["is_system", "weights", "updated_at"])

    for key, description in DECLARED_FLAGS:
        FeatureFlag.objects.get_or_create(
            key=key,
            defaults={
                "description": description,
                "enabled": True,
                "rollout_percent": 100,
                "variants": [],
            },
        )


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0011_auditevent_featureflag_default"),
        ("core", "0016_seed_harmonious_12_weights"),
        ("suggestions", "0056_add_char_ngram_vector_to_contentitem"),
    ]

    operations = [
        migrations.RunPython(seed_defaults, reverse_code=migrations.RunPython.noop),
    ]
