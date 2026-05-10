"""Seed the same-day Pyroscope hotspot detector threshold.

The week-over-week regression detector in pyroscope_picker.py needs 7
days of profile history before it produces useful AutoIssues. The
same-day hotspot detector added in plan
`does-adding-qodana-make-swift-wall.md` Stream 2 produces findings from
day one — any function whose self-CPU exceeds this percent of the total
runtime in the last 1 hour becomes an AutoIssue with kind='hotspot'.

Default 5.0 (= 5 percent) — the same threshold the existing
week-over-week detector uses for share-of-total. Per DEFAULT-ON-RULE
this seeds via get_or_create so an operator override is preserved
across re-runs.
"""

from django.db import migrations


DEFAULTS = {
    "pyroscope.hotspot_pct_threshold": {
        "value": "5.0",
        "value_type": "float",
        "category": "observability",
        "description": (
            "Pyroscope same-day hotspot detector promotes any function "
            "whose self-CPU exceeds this percent of total runtime in "
            "the last 1 hour. Default 5.0 (5 percent). Lower = more "
            "AutoIssues filed."
        ),
    },
    "pyroscope.hotspot_window_seconds": {
        "value": "3600",
        "value_type": "int",
        "category": "observability",
        "description": (
            "Time window the Pyroscope hotspot detector queries. "
            "Default 3600 seconds (1 hour). Tunable for noisy traffic."
        ),
    },
}


def seed_defaults(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    for key, meta in DEFAULTS.items():
        AppSetting.objects.get_or_create(key=key, defaults=meta)


def unseed(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.filter(key__in=DEFAULTS.keys()).delete()


class Migration(migrations.Migration):

    dependencies = [
        ("auto_issues", "0003_autoissue_canonical_fingerprint_and_more"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_defaults, unseed),
    ]
