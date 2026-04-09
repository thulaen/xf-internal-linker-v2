from django.db import migrations


def upsert_health_settings(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")

    settings = [
        (
            "health.ga4_stale_threshold_hours",
            "72",
            "int",
            "analytics",
            "GA4 data freshness threshold (hours)",
        ),
        (
            "health.gsc_stale_threshold_hours",
            "72",
            "int",
            "analytics",
            "GSC data freshness threshold (hours)",
        ),
        (
            "health.xenforo_stale_threshold_hours",
            "48",
            "int",
            "sync",
            "XenForo sync staleness threshold (hours)",
        ),
        (
            "health.wordpress_stale_threshold_hours",
            "48",
            "int",
            "sync",
            "WordPress sync staleness threshold (hours)",
        ),
        (
            "health.pipeline_suggestion_drop_threshold_pct",
            "30",
            "int",
            "performance",
            "Alert if pipeline suggestions drop by more than X% vs average",
        ),
        (
            "health.check_interval_minutes",
            "5",
            "int",
            "performance",
            "Frequency of background health checks",
        ),
    ]

    for key, value, value_type, category, description in settings:
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "value_type": value_type,
                "category": category,
                "description": description,
                "is_secret": False,
            },
        )


def remove_health_settings(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    keys = [
        "health.ga4_stale_threshold_hours",
        "health.gsc_stale_threshold_hours",
        "health.xenforo_stale_threshold_hours",
        "health.wordpress_stale_threshold_hours",
        "health.pipeline_suggestion_drop_threshold_pct",
        "health.check_interval_minutes",
    ]
    AppSetting.objects.filter(key__in=keys).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0001_initial"),
        ("core", "0001_initial"),  # Assuming core 0001 has AppSetting
    ]

    operations = [
        migrations.RunPython(upsert_health_settings, remove_health_settings),
    ]
