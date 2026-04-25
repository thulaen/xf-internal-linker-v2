"""Move ``fasttext_langid.model_path`` from /app to /opt.

The Wire-phase backend Dockerfile downloads ``lid.176.bin`` to
``/opt/models/lid.176.bin``. The original 0043 seed migration
mistakenly pointed the AppSetting at ``/app/models/lid.176.bin``,
but the dev/prod compose stack bind-mounts ``./backend → /app``,
which hides anything baked into ``/app`` at image build time.

This migration re-points the AppSetting at the correct location.
Idempotent — re-running on an already-fixed install is a no-op
that simply refreshes the description.
"""

from __future__ import annotations

from django.db import migrations


def fix_fasttext_path(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.update_or_create(
        key="fasttext_langid.model_path",
        defaults={
            "value": "/opt/models/lid.176.bin",
            "description": (
                "Pick #14 FastText LangID model path. Downloaded by "
                "the Dockerfile to /opt (NOT /app, because the "
                "compose stack bind-mounts ./backend → /app)."
            ),
            "value_type": "str",
            "category": "parse",
        },
    )


def reverse_fix(apps, schema_editor):
    AppSetting = apps.get_model("core", "AppSetting")
    AppSetting.objects.update_or_create(
        key="fasttext_langid.model_path",
        defaults={
            "value": "/app/models/lid.176.bin",
            "description": "Pick #14 FastText LangID model path.",
            "value_type": "str",
            "category": "parse",
        },
    )


class Migration(migrations.Migration):
    dependencies = [
        ("suggestions", "0043_seed_phase6_pick_defaults"),
        ("core", "0001_initial"),
    ]

    operations = [
        migrations.RunPython(fix_fasttext_path, reverse_fix),
    ]
