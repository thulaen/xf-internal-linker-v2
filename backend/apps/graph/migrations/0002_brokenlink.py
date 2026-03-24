import uuid

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("content", "0001_initial"),
        ("graph", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="BrokenLink",
            fields=[
                ("created_at", models.DateTimeField(auto_now_add=True, help_text="Timestamp when this record was created.")),
                ("updated_at", models.DateTimeField(auto_now=True, help_text="Timestamp when this record was last modified.")),
                ("broken_link_id", models.UUIDField(default=uuid.uuid4, editable=False, help_text="Stable UUID used by the API and Angular frontend.", primary_key=True, serialize=False)),
                ("url", models.URLField(help_text="The URL found in the source content.", max_length=2048)),
                ("http_status", models.IntegerField(default=0, help_text="Last HTTP status code seen for this URL. 0 means connection error or timeout.")),
                ("redirect_url", models.URLField(blank=True, default="", help_text="Redirect destination when the URL responds with a redirect status.", max_length=2048)),
                ("first_detected_at", models.DateTimeField(auto_now_add=True, help_text="When this issue was first detected by the scanner.")),
                ("last_checked_at", models.DateTimeField(auto_now=True, help_text="When the scanner last checked this URL.")),
                ("status", models.CharField(choices=[("open", "Open"), ("ignored", "Ignored"), ("fixed", "Fixed")], db_index=True, default="open", help_text="Manual review state for this broken-link record.", max_length=20)),
                ("notes", models.TextField(blank=True, help_text="Reviewer notes about why the record was ignored or fixed.")),
                ("source_content", models.ForeignKey(help_text="The content item where this URL was found.", on_delete=django.db.models.deletion.CASCADE, related_name="broken_links", to="content.contentitem")),
            ],
            options={
                "verbose_name": "Broken Link",
                "verbose_name_plural": "Broken Links",
                "ordering": ["status", "-last_checked_at", "-first_detected_at"],
            },
        ),
        migrations.AddIndex(
            model_name="brokenlink",
            index=models.Index(fields=["status", "http_status"], name="graph_broke_status_11a3c0_idx"),
        ),
        migrations.AddIndex(
            model_name="brokenlink",
            index=models.Index(fields=["source_content", "status"], name="graph_broke_source__72a24f_idx"),
        ),
        migrations.AddConstraint(
            model_name="brokenlink",
            constraint=models.UniqueConstraint(fields=("source_content", "url"), name="graph_unique_broken_link_source_url"),
        ),
    ]
