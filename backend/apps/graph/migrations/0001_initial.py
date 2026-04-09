"""Graph app initial migration."""

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True
    dependencies = [
        ("content", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExistingLink",
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
                (
                    "anchor_text",
                    models.CharField(
                        blank=True,
                        help_text="The anchor text used for this link.",
                        max_length=500,
                    ),
                ),
                (
                    "discovered_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="When this link was first detected.",
                    ),
                ),
                (
                    "from_content_item",
                    models.ForeignKey(
                        help_text="The content item that contains this link.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="outgoing_links",
                        to="content.contentitem",
                    ),
                ),
                (
                    "to_content_item",
                    models.ForeignKey(
                        help_text="The content item being linked to.",
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="incoming_links",
                        to="content.contentitem",
                    ),
                ),
            ],
            options={
                "verbose_name": "Existing Link",
                "verbose_name_plural": "Existing Links",
                "unique_together": {
                    ("from_content_item", "to_content_item", "anchor_text")
                },
            },
        ),
        migrations.AddIndex(
            model_name="existinglink",
            index=models.Index(fields=["to_content_item"], name="graph_link_to_idx"),
        ),
        migrations.AddIndex(
            model_name="existinglink",
            index=models.Index(
                fields=["from_content_item"], name="graph_link_from_idx"
            ),
        ),
    ]
