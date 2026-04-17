# Phase DC / Gap 119 — EntityVersion generic snapshot table.

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0005_webvital_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="EntityVersion",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("target_type", models.CharField(db_index=True, max_length=60)),
                ("target_id", models.CharField(db_index=True, max_length=100)),
                ("payload", models.JSONField(default=dict)),
                ("actor", models.CharField(blank=True, max_length=100)),
                ("note", models.CharField(blank=True, max_length=255)),
            ],
            options={
                "verbose_name": "Entity Version",
                "verbose_name_plural": "Entity Versions",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["target_type", "target_id", "-created_at"],
                        name="audit_ev_target_created_idx",
                    ),
                ],
            },
        ),
    ]
