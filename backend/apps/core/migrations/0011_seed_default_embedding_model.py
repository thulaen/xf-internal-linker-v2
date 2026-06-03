"""Persist the default embedding model for installs that do not have one yet."""

from django.db import migrations


DEFAULT_EMBEDDING_MODEL_ROW = {
    "key": "embedding.model",
    "value": "text-embedding-3-small",
    "value_type": "str",
    "category": "ml",
    "description": (
        "Default paid embedding model used unless the operator promotes a "
        "different champion."
    ),
}


def seed_default_embedding_model(apps, schema_editor):
    if apps is None:
        from apps.core.models import AppSetting
    else:
        AppSetting = apps.get_model("core", "AppSetting")

    if AppSetting.objects.filter(key=DEFAULT_EMBEDDING_MODEL_ROW["key"]).exists():
        return

    AppSetting.objects.create(
        key=DEFAULT_EMBEDDING_MODEL_ROW["key"],
        value=DEFAULT_EMBEDDING_MODEL_ROW["value"],
        value_type=DEFAULT_EMBEDDING_MODEL_ROW["value_type"],
        category=DEFAULT_EMBEDDING_MODEL_ROW["category"],
        description=DEFAULT_EMBEDDING_MODEL_ROW["description"],
        is_secret=False,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0010_runtimeauditlog_helpernode_accepting_work_and_more"),
    ]

    operations = [
        migrations.RunPython(
            seed_default_embedding_model,
            reverse_code=migrations.RunPython.noop,
        ),
    ]
