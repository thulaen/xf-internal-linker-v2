"""Seed the Prophet spike-detector settings, default-on.

The GSC traffic-spike detector now forecasts each page's weekly rhythm
with Prophet instead of comparing against a flat 7-day average. These
five settings tune it and all ship with sensible non-zero values, so
the feature is on out of the box (default-on rule). Operators can adjust
them later via AppSetting without a code change.

Only ``get_or_create`` is used — an operator-overridden value is never
clobbered.
"""

from django.db import migrations


NEW_VALUES = {
    "spike_detection.history_days": "90",          # days of history Prophet fits
    "spike_detection.noise_floor_clicks": "10",    # ignore pages below this on the target day
    "spike_detection.upper_bound_factor": "1.2",   # actual must exceed forecast upper bound by 20%
    "spike_detection.prophet_max_items": "200",    # cap on per-page fits per run
    "spike_detection.min_active_days": "14",        # skip pages with too few active days to model
}


def seed_spike_settings(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    for key, value in NEW_VALUES.items():
        AppSetting.objects.get_or_create(key=key, defaults={"value": value})


class Migration(migrations.Migration):
    dependencies = [
        ("analytics", "0011_add_matomo_daily_traffic"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(seed_spike_settings, reverse_code=migrations.RunPython.noop),
    ]
