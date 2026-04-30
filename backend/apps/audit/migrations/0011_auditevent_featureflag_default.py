from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0010_featureflag_featureflagexposure"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditEvent",
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
                ("action", models.CharField(db_index=True, max_length=80)),
                ("subject_type", models.CharField(db_index=True, max_length=80)),
                (
                    "subject_id",
                    models.CharField(blank=True, db_index=True, max_length=120),
                ),
                ("actor", models.CharField(blank=True, db_index=True, max_length=150)),
                ("message", models.TextField()),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("ip_address", models.GenericIPAddressField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                "verbose_name": "Audit Event",
                "verbose_name_plural": "Audit Events",
                "ordering": ["-created_at"],
                "indexes": [
                    models.Index(
                        fields=["subject_type", "subject_id"],
                        name="audit_evt_subject_idx",
                    ),
                    models.Index(
                        fields=["action", "-created_at"],
                        name="audit_evt_action_idx",
                    ),
                ],
            },
        ),
        migrations.AlterField(
            model_name="featureflag",
            name="enabled",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="errorlog",
            name="severity",
            field=models.CharField(
                choices=[
                    ("critical", "Critical"),
                    ("high", "High"),
                    ("medium", "Medium"),
                    ("warning", "Warning"),
                    ("low", "Low"),
                ],
                db_index=True,
                default="medium",
                max_length=10,
            ),
        ),
    ]
