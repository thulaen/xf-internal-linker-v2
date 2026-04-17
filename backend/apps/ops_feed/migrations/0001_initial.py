# Phase OF — initial migration for the Operations Feed.

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="OperationEvent",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True, primary_key=True, serialize=False, verbose_name="ID"
                    ),
                ),
                ("timestamp", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("event_type", models.CharField(db_index=True, max_length=60)),
                (
                    "source",
                    models.CharField(
                        db_index=True,
                        help_text="Which subsystem emitted this (e.g. 'pipeline', 'crawler').",
                        max_length=60,
                    ),
                ),
                (
                    "plain_english",
                    models.TextField(
                        help_text="Operator-facing sentence the UI renders verbatim."
                    ),
                ),
                (
                    "severity",
                    models.CharField(
                        choices=[
                            ("info", "Info"),
                            ("warning", "Warning"),
                            ("error", "Error"),
                            ("success", "Success"),
                        ],
                        db_index=True,
                        default="info",
                        max_length=10,
                    ),
                ),
                ("related_entity_type", models.CharField(blank=True, db_index=True, max_length=60)),
                ("related_entity_id", models.CharField(blank=True, db_index=True, max_length=100)),
                ("runtime_context", models.JSONField(blank=True, default=dict)),
                ("dedup_key", models.CharField(blank=True, db_index=True, max_length=100)),
                ("occurrence_count", models.IntegerField(default=1)),
                ("error_log_id", models.IntegerField(blank=True, db_index=True, null=True)),
            ],
            options={
                "verbose_name": "Operation Event",
                "verbose_name_plural": "Operation Events",
                "ordering": ["-timestamp"],
                "indexes": [
                    models.Index(fields=["severity", "-timestamp"], name="ofeed_sev_ts_idx"),
                    models.Index(fields=["dedup_key", "-timestamp"], name="ofeed_dedup_idx"),
                ],
            },
        ),
    ]
