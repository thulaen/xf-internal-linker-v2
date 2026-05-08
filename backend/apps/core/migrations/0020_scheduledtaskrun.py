"""Migration: add the ScheduledTaskRun table for the sentient-schedules tracker.

Hand-rolled (not auto-generated) so we control the index and constraint names
explicitly. The unique constraint on (task_name, scheduled_for) is what makes
the missed-schedule recovery sweep idempotent — re-running it doesn't insert
duplicate rows for the same slot.
"""

import django.db.models.deletion  # noqa: F401  (kept for parity with auto-generated migrations)
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0019_seed_goldmidi_domains"),
    ]

    operations = [
        migrations.CreateModel(
            name="ScheduledTaskRun",
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
                ("task_name", models.CharField(db_index=True, max_length=200)),
                ("scheduled_for", models.DateTimeField(db_index=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("finished_at", models.DateTimeField(blank=True, null=True)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "pending"),
                            ("running", "running"),
                            ("succeeded", "succeeded"),
                            ("failed", "failed"),
                            ("skipped", "skipped"),
                        ],
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("last_error", models.TextField(blank=True, default="")),
                (
                    "recovered_run",
                    models.BooleanField(
                        default=False,
                        help_text="True if this run was fired by the missed-schedule recovery sweep.",
                    ),
                ),
                ("payload", models.JSONField(blank=True, default=dict)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "verbose_name": "Scheduled task run",
                "verbose_name_plural": "Scheduled task runs",
                "indexes": [
                    models.Index(
                        fields=["task_name", "-scheduled_for"],
                        name="strun_task_recent_idx",
                    ),
                    models.Index(fields=["status"], name="strun_status_idx"),
                ],
                "constraints": [
                    models.UniqueConstraint(
                        fields=["task_name", "scheduled_for"],
                        name="strun_unique_task_per_slot",
                    ),
                ],
            },
        ),
    ]
