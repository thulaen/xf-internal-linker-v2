"""Rename the django_celery_beat PeriodicTask row from
``monthly-cs-weight-tune`` to ``monthly-python-weight-tune`` so it stays
in sync with the renamed Beat schedule key in
``backend/config/settings/celery_schedules.py`` and
``backend/config/catchup_registry.py``.

DatabaseScheduler reads PeriodicTask rows directly. Without this rename,
the previously-seeded row would orphan and the catch-up registry lookup
in ``backend/config/catchup.py`` would never match the new key.
"""

from django.db import migrations


OLD_NAME = "monthly-cs-weight-tune"
NEW_NAME = "monthly-python-weight-tune"


def rename_forward(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=OLD_NAME).update(name=NEW_NAME)


def rename_reverse(apps, schema_editor):
    PeriodicTask = apps.get_model("django_celery_beat", "PeriodicTask")
    PeriodicTask.objects.filter(name=NEW_NAME).update(name=OLD_NAME)


class Migration(migrations.Migration):
    dependencies = [
        ("pipeline", "0002_embedding_infra"),
        ("django_celery_beat", "0019_alter_periodictasks_options"),
    ]

    operations = [
        migrations.RunPython(rename_forward, reverse_code=rename_reverse),
    ]
