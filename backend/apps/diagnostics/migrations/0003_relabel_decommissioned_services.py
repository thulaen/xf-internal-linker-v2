"""Relabel decommissioned ServiceStatusSnapshot service entries.

Per ISS-009, the keys ``http_worker`` and ``scheduler_lane`` are kept in
the choices list to avoid migrating historical rows. Only the
human-readable label is updated to drop the misleading "C#" wording now
that the HTTP worker is decommissioned and Celery Beat owns the
scheduler.
"""

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("diagnostics", "0002_expand_service_status_choices"),
    ]

    operations = [
        migrations.AlterField(
            model_name="servicestatussnapshot",
            name="service_name",
            field=models.CharField(
                choices=[
                    ("django", "Django API"),
                    ("postgresql", "PostgreSQL"),
                    ("redis", "Redis"),
                    ("celery_worker", "Celery Worker"),
                    ("celery_beat", "Celery Beat"),
                    ("channels", "Channels / WebSockets"),
                    ("http_worker", "Decommissioned HTTP worker (legacy)"),
                    ("xenforo_sync", "XenForo Sync"),
                    ("wordpress_sync", "WordPress Sync"),
                    ("ga4", "GA4"),
                    ("gsc", "GSC"),
                    ("analytics_app", "Analytics App"),
                    ("r_analytics", "R Analytics Service"),
                    ("r_weight_tuning", "R Auto-Weight Tuning"),
                    ("local_model", "Local Embedding/Model Runtime"),
                    ("matomo", "Matomo"),
                    ("runtime_lanes", "Runtime Lanes"),
                    ("scheduler_lane", "Task Scheduler"),
                    ("native_scoring", "Native C++ Scoring"),
                    ("slate_diversity_runtime", "Slate Diversity Runtime"),
                    ("embedding_specialist", "Python Embedding Specialist"),
                ],
                db_index=True,
                max_length=50,
            ),
        ),
    ]
