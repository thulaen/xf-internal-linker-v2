import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("content", "0014_fr014_near_duplicate_clustering"),
    ]

    operations = [
        migrations.CreateModel(
            name="SessionCoOccurrenceRun",
            fields=[
                (
                    "run_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("running", "Running"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        default="running",
                        max_length=20,
                    ),
                ),
                ("data_window_start", models.DateField()),
                ("data_window_end", models.DateField()),
                ("sessions_processed", models.IntegerField(default=0)),
                ("pairs_written", models.IntegerField(default=0)),
                ("ga4_rows_fetched", models.IntegerField(default=0)),
                ("started_at", models.DateTimeField(auto_now_add=True)),
                ("completed_at", models.DateTimeField(blank=True, null=True)),
                ("error_message", models.TextField(blank=True)),
            ],
            options={"ordering": ["-started_at"]},
        ),
        migrations.CreateModel(
            name="BehavioralHub",
            fields=[
                (
                    "hub_id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                ("name", models.CharField(max_length=200)),
                (
                    "detection_method",
                    models.CharField(
                        choices=[
                            (
                                "threshold_connected_components",
                                "Threshold Connected Components",
                            ),
                            ("manual", "Manual"),
                        ],
                        default="threshold_connected_components",
                        max_length=40,
                    ),
                ),
                (
                    "min_jaccard_used",
                    models.FloatField(
                        help_text="Minimum Jaccard threshold used when this hub was detected."
                    ),
                ),
                ("member_count", models.IntegerField(default=0)),
                (
                    "auto_link_enabled",
                    models.BooleanField(
                        default=False,
                        help_text="When true, hub-pair suggestions are flagged with candidate_origin=behavioral_hub.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
            options={"ordering": ["-member_count", "name"]},
        ),
        migrations.CreateModel(
            name="SessionCoOccurrencePair",
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
                    "source_content_item",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cooccurrence_as_source",
                        to="content.contentitem",
                    ),
                ),
                (
                    "dest_content_item",
                    models.ForeignKey(
                        db_index=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="cooccurrence_as_dest",
                        to="content.contentitem",
                    ),
                ),
                (
                    "co_session_count",
                    models.IntegerField(
                        help_text="Number of sessions in which both articles were viewed."
                    ),
                ),
                (
                    "source_session_count",
                    models.IntegerField(
                        help_text="Number of sessions in which the source article was viewed."
                    ),
                ),
                (
                    "dest_session_count",
                    models.IntegerField(
                        help_text="Number of sessions in which the destination article was viewed."
                    ),
                ),
                (
                    "jaccard_similarity",
                    models.FloatField(
                        db_index=True,
                        help_text="co_session_count / (source + dest - co). Bounded [0, 1].",
                    ),
                ),
                (
                    "lift",
                    models.FloatField(
                        help_text="P(A\u2229B) / (P(A) \u00d7 P(B)). Values > 1 mean articles are co-read more than chance."
                    ),
                ),
                ("last_computed_at", models.DateTimeField(auto_now=True)),
                ("data_window_start", models.DateField()),
                ("data_window_end", models.DateField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
        migrations.CreateModel(
            name="BehavioralHubMembership",
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
                    "hub",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="memberships",
                        to="cooccurrence.behavioralhub",
                    ),
                ),
                (
                    "content_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="behavioral_hub_memberships",
                        to="content.contentitem",
                    ),
                ),
                (
                    "membership_source",
                    models.CharField(
                        choices=[
                            ("auto_detected", "Auto Detected"),
                            ("manual_add", "Manually Added"),
                            ("manual_remove_override", "Manually Removed (Override)"),
                        ],
                        default="auto_detected",
                        max_length=30,
                    ),
                ),
                (
                    "co_occurrence_strength",
                    models.FloatField(
                        default=0.0,
                        help_text="Average Jaccard similarity to other hub members.",
                    ),
                ),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
        ),
        migrations.AddConstraint(
            model_name="sessioncooccurrencepair",
            constraint=models.UniqueConstraint(
                fields=["source_content_item", "dest_content_item"],
                name="unique_cooccurrence_pair",
            ),
        ),
        migrations.AddIndex(
            model_name="sessioncooccurrencepair",
            index=models.Index(
                fields=["source_content_item", "jaccard_similarity"],
                name="cooccurrenc_source__idx",
            ),
        ),
        migrations.AddIndex(
            model_name="sessioncooccurrencepair",
            index=models.Index(
                fields=["dest_content_item", "jaccard_similarity"],
                name="cooccurrenc_dest_co_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="behavioralhubmembership",
            constraint=models.UniqueConstraint(
                fields=["hub", "content_item"], name="unique_hub_membership"
            ),
        ),
    ]
