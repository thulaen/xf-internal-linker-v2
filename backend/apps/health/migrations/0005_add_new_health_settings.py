from django.db import migrations


def add_health_settings(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")

    settings = [
        ("health.pipeline_failure_rate_warning_pct", "20", "int", "performance", "Warn if pipeline run failure rate exceeds this % (7-day window)"),
        ("health.pipeline_warning_hours_no_run", "24", "int", "performance", "Warn if no pipeline run has started in this many hours"),
        ("health.celery_queue_warning_depth", "50", "int", "performance", "Warn if any Celery queue has more than this many pending tasks"),
        ("health.celery_queue_error_depth", "200", "int", "performance", "Error if any Celery queue exceeds this many pending tasks"),
        ("health.beat_stale_threshold_minutes", "60", "int", "performance", "Warn if Celery Beat last fired more than this many minutes ago"),
        ("health.disk_warning_pct", "80", "int", "performance", "Warn if disk usage exceeds this percentage"),
        ("health.disk_error_pct", "90", "int", "performance", "Error if disk usage exceeds this percentage"),
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
    AppSetting.objects.filter(key__in=[
        "health.pipeline_failure_rate_warning_pct",
        "health.pipeline_warning_hours_no_run",
        "health.celery_queue_warning_depth",
        "health.celery_queue_error_depth",
        "health.beat_stale_threshold_minutes",
        "health.disk_warning_pct",
        "health.disk_error_pct",
    ]).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("health", "0004_servicehealthrecord_service_description_and_more"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(add_health_settings, remove_health_settings),
    ]
