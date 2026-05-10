"""Add ``loki`` to AutoIssue.source choices + seed loki_picker thresholds.

The Loki picker (added 2026-05-10 per plan
``does-adding-qodana-make-swift-wall.md`` Stream 4) reads container
stdout logs from Loki via LogQL and promotes:

  - **hot patterns** — repeated WARN/ERROR lines whose count in a 24 h
    window exceeds a threshold. Works from day one as soon as Alloy
    starts shipping logs.
  - **warn bursts** — short-window rate spikes versus a 24 h baseline.
    Needs ≥1 day of history to be useful but the picker no-ops cleanly
    when the baseline is empty.

Per DEFAULT-ON-RULE every setting is seeded ON with a non-zero starting
value via ``get_or_create`` so a fresh DB / restore preserves operator
overrides.
"""

from django.db import migrations, models


LOKI_DEFAULTS = {
    "loki.api_url": {
        "value": "http://loki:3100",
        "value_type": "string",
        "category": "observability",
        "description": (
            "Base URL of the Loki HTTP API the loki_picker queries. "
            "Default `http://loki:3100` matches the docker-compose "
            "service. Override only when running Loki on a non-default "
            "port or remote host."
        ),
    },
    "loki.scan_window_seconds": {
        "value": "86400",
        "value_type": "int",
        "category": "observability",
        "description": (
            "Time window (seconds) the loki_picker scans for hot "
            "patterns. Default 86400 (24 h)."
        ),
    },
    "loki.hot_pattern_min_count": {
        "value": "10",
        "value_type": "int",
        "category": "observability",
        "description": (
            "Minimum occurrence count for a normalized log line "
            "fingerprint to be promoted as kind='hot_pattern'. Default "
            "10 occurrences in the scan window."
        ),
    },
    "loki.warn_burst_multiplier": {
        "value": "3.0",
        "value_type": "float",
        "category": "observability",
        "description": (
            "Burst detector: a 1 h WARN/ERROR rate at least this "
            "multiple of the 24 h average is promoted as "
            "kind='warn_burst'. Default 3.0."
        ),
    },
    "loki.max_lines_per_query": {
        "value": "5000",
        "value_type": "int",
        "category": "observability",
        "description": (
            "Cap on how many raw log lines the picker pulls per LogQL "
            "query. Anti-bloat guarantee. Default 5000."
        ),
    },
}


def seed_loki_settings(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    for key, meta in LOKI_DEFAULTS.items():
        AppSetting.objects.get_or_create(key=key, defaults=meta)


def unseed_loki_settings(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.filter(key__in=LOKI_DEFAULTS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('auto_issues', '0004_seed_pyroscope_hotspot_threshold'),
        ('core', '0001_initial'),
    ]

    operations = [
        migrations.AlterField(
            model_name='autoissue',
            name='source',
            field=models.CharField(
                choices=[
                    ('glitchtip', 'GlitchTip'),
                    ('pyroscope', 'Pyroscope'),
                    ('loki', 'Loki'),
                    ('agent', 'Agent find'),
                ],
                db_index=True,
                max_length=16,
            ),
        ),
        migrations.RunPython(seed_loki_settings, unseed_loki_settings),
    ]
