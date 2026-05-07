"""Seed the goldmidi.com production domain values into AppSetting.

Operator instruction (2026-05-07): "the domains are goldmidi.com/community/
for xenforo and misc.goldmidi.com for wp." The Django settings layer
already reads ``XENFORO_BASE_URL`` and ``WORDPRESS_BASE_URL`` from env
vars (`backend/config/settings/base.py:488,495`), but the Settings UI
reads from the AppSetting table — this migration seeds the rows so the
operator sees the correct values on `/settings` without an env-var
round-trip.

Idempotent via ``get_or_create``: an operator override on either key
is preserved. Fresh installs and pristine installs that re-apply the
Recommended preset get the new values.
"""

from django.db import migrations


NEW_VALUES = {
    # XenForo forum at goldmidi.com/community/
    "xenforo.base_url": "https://goldmidi.com/community",
    # WordPress site at misc.goldmidi.com (cross-linking source).
    "wordpress.base_url": "https://misc.goldmidi.com",
}


def seed_goldmidi_domains(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    for key, value in NEW_VALUES.items():
        AppSetting.objects.get_or_create(
            key=key,
            defaults={"value": value},
        )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0018_dashboard_suggestion_counts_mv"),
    ]

    operations = [
        migrations.RunPython(
            seed_goldmidi_domains,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
