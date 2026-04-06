"""Lower the default max_existing_links_per_host from 3 to 2.

With 60k+ threads, a cap of 2 outgoing links per host page is more
conservative and reduces the risk of tripping spam heuristics.

Only updates the row if the current value is still the original seed
value ("3"), so user-customised values are preserved.
"""

from django.db import migrations


def lower_max_links(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.filter(
        key="spam_guards.max_existing_links_per_host",
        value="3",
    ).update(value="2")


def restore_max_links(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.filter(
        key="spam_guards.max_existing_links_per_host",
        value="2",
    ).update(value="3")


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_seed_spam_guard_defaults"),
    ]

    operations = [
        migrations.RunPython(lower_max_links, restore_max_links),
    ]
