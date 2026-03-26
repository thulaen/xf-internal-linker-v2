import uuid
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="SyncJob",
            fields=[
                ("job_id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(
                    choices=[
                        ("pending", "Pending"),
                        ("running", "Running"),
                        ("completed", "Completed"),
                        ("failed", "Failed"),
                    ],
                    default="pending",
                    max_length=20,
                )),
                ("source", models.CharField(
                    choices=[
                        ("api", "XenForo API"),
                        ("jsonl", "JSONL File"),
                        ("wp", "WordPress API"),
                    ],
                    max_length=20,
                )),
                ("mode", models.CharField(max_length=20)),
                ("file_name", models.CharField(blank=True, max_length=255, null=True)),
                ("progress", models.FloatField(default=0.0)),
                ("message", models.CharField(blank=True, max_length=500)),
                ("items_synced", models.IntegerField(default=0)),
                ("items_updated", models.IntegerField(default=0)),
                ("error_message", models.TextField(blank=True)),
                ("started_at", models.DateTimeField(blank=True, null=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={
                "ordering": ["-created_at"],
            },
        ),
    ]
