"""
Content app initial migration.

The first operation enables the pgvector PostgreSQL extension (idempotent).
This MUST run before any table with a VectorField column is created.
"""

import django.db.models.deletion
from django.db import migrations, models
from pgvector.django import VectorExtension, VectorField


class Migration(migrations.Migration):
    initial = True

    dependencies = []

    operations = [
        # Enable pgvector extension — must be first
        VectorExtension(),
        migrations.CreateModel(
            name="ScopeItem",
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
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last modified.",
                    ),
                ),
                (
                    "scope_id",
                    models.IntegerField(
                        help_text="The ID of this node/category in XenForo or WordPress."
                    ),
                ),
                (
                    "scope_type",
                    models.CharField(
                        choices=[
                            ("node", "Forum Node"),
                            ("resource_category", "Resource Category"),
                            ("wp_category", "WordPress Category"),
                        ],
                        help_text="Type of scope.",
                        max_length=30,
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="Display name of the node or category.",
                        max_length=500,
                    ),
                ),
                (
                    "is_enabled",
                    models.BooleanField(
                        default=True,
                        help_text="Only enabled scopes are included in pipeline runs.",
                    ),
                ),
                (
                    "content_count",
                    models.IntegerField(
                        default=0,
                        help_text="Cached count of content items in this scope.",
                    ),
                ),
                (
                    "display_order",
                    models.IntegerField(
                        default=0, help_text="Sort order for display in the UI."
                    ),
                ),
                (
                    "metadata",
                    models.JSONField(
                        blank=True,
                        default=dict,
                        help_text="Extra data from the XenForo API response.",
                    ),
                ),
                (
                    "parent",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.SET_NULL,
                        related_name="children",
                        to="content.scopeitem",
                        help_text="Parent scope item.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Scope Item",
                "verbose_name_plural": "Scope Items",
                "unique_together": {("scope_id", "scope_type")},
            },
        ),
        migrations.AddIndex(
            model_name="scopeitem",
            index=models.Index(
                fields=["scope_type", "is_enabled"],
                name="content_scopeitem_type_enabled_idx",
            ),
        ),
        migrations.CreateModel(
            name="ContentItem",
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
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last modified.",
                    ),
                ),
                (
                    "content_id",
                    models.IntegerField(
                        help_text="The original ID in XenForo or WordPress."
                    ),
                ),
                (
                    "content_type",
                    models.CharField(
                        choices=[
                            ("thread", "Forum Thread"),
                            ("resource", "Resource"),
                            ("wp_post", "WordPress Post"),
                        ],
                        help_text="Content type.",
                        max_length=30,
                    ),
                ),
                (
                    "title",
                    models.CharField(
                        help_text="The title of the thread or resource.", max_length=500
                    ),
                ),
                (
                    "url",
                    models.URLField(
                        blank=True,
                        help_text="Canonical URL on the live forum.",
                        max_length=1000,
                    ),
                ),
                (
                    "distilled_text",
                    models.TextField(
                        blank=True,
                        help_text="Compact topical summary used for embedding.",
                    ),
                ),
                (
                    "distill_method",
                    models.CharField(
                        choices=[
                            ("title_plus_body", "Title + Body"),
                            ("title_only", "Title Only"),
                        ],
                        default="title_plus_body",
                        help_text="How distilled_text was generated.",
                        max_length=50,
                    ),
                ),
                (
                    "content_hash",
                    models.CharField(
                        blank=True,
                        help_text="SHA-256 hash of the raw post body.",
                        max_length=64,
                    ),
                ),
                (
                    "pagerank_score",
                    models.FloatField(
                        db_index=True,
                        default=0.0,
                        help_text="PageRank authority score.",
                    ),
                ),
                (
                    "velocity_score",
                    models.FloatField(
                        db_index=True,
                        default=0.0,
                        help_text="Recency/engagement velocity score.",
                    ),
                ),
                (
                    "embedding",
                    VectorField(
                        blank=True,
                        dimensions=384,
                        help_text="384-dimension embedding for pgvector similarity search.",
                        null=True,
                    ),
                ),
                (
                    "view_count",
                    models.IntegerField(
                        default=0, help_text="Number of views on the live forum."
                    ),
                ),
                (
                    "reply_count",
                    models.IntegerField(default=0, help_text="Number of replies."),
                ),
                (
                    "download_count",
                    models.IntegerField(
                        default=0, help_text="Download count (resources only)."
                    ),
                ),
                (
                    "xf_post_id",
                    models.IntegerField(
                        blank=True,
                        null=True,
                        help_text="XenForo post ID of the first post.",
                    ),
                ),
                (
                    "xf_update_id",
                    models.IntegerField(
                        blank=True, null=True, help_text="XenForo update ID."
                    ),
                ),
                (
                    "post_date",
                    models.DateTimeField(
                        blank=True, null=True, help_text="When originally posted."
                    ),
                ),
                (
                    "last_post_date",
                    models.DateTimeField(
                        blank=True, null=True, help_text="When last reply was posted."
                    ),
                ),
                (
                    "is_deleted",
                    models.BooleanField(
                        default=False, help_text="True if deleted on the live forum."
                    ),
                ),
                (
                    "fetched_at",
                    models.DateTimeField(
                        auto_now=True, help_text="Last time synced from XenForo API."
                    ),
                ),
                (
                    "scope",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="content_items",
                        to="content.scopeitem",
                        help_text="The forum node or category this content belongs to.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Content Item",
                "verbose_name_plural": "Content Items",
                "unique_together": {("content_id", "content_type")},
            },
        ),
        migrations.AddIndex(
            model_name="contentitem",
            index=models.Index(
                fields=["content_type", "pagerank_score"],
                name="content_ci_type_pagerank_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="contentitem",
            index=models.Index(
                fields=["content_type", "velocity_score"],
                name="content_ci_type_velocity_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="contentitem",
            index=models.Index(fields=["is_deleted"], name="content_ci_deleted_idx"),
        ),
        migrations.CreateModel(
            name="Post",
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
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created.",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp when this record was last modified.",
                    ),
                ),
                (
                    "raw_bbcode",
                    models.TextField(
                        help_text="Original BBCode from XenForo, unmodified."
                    ),
                ),
                (
                    "clean_text",
                    models.TextField(
                        blank=True, help_text="Plain text after stripping BBCode tags."
                    ),
                ),
                (
                    "char_count",
                    models.IntegerField(
                        default=0, help_text="Character count of clean_text."
                    ),
                ),
                (
                    "word_count",
                    models.IntegerField(
                        default=0, help_text="Word count of clean_text."
                    ),
                ),
                (
                    "xf_post_id",
                    models.IntegerField(
                        blank=True, null=True, help_text="XenForo post ID."
                    ),
                ),
                (
                    "xf_update_id",
                    models.IntegerField(
                        blank=True, null=True, help_text="XenForo update ID."
                    ),
                ),
                (
                    "last_edit_date",
                    models.DateTimeField(
                        blank=True,
                        null=True,
                        help_text="When this post was last edited.",
                    ),
                ),
                (
                    "content_item",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="post",
                        to="content.contentitem",
                        help_text="The content item this post belongs to.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Post",
                "verbose_name_plural": "Posts",
            },
        ),
        migrations.CreateModel(
            name="Sentence",
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
                    "text",
                    models.TextField(
                        help_text="The sentence text as extracted by spaCy."
                    ),
                ),
                (
                    "position",
                    models.IntegerField(
                        help_text="Zero-based sentence index within the post."
                    ),
                ),
                (
                    "char_count",
                    models.IntegerField(help_text="Character length of this sentence."),
                ),
                (
                    "start_char",
                    models.IntegerField(
                        help_text="Character offset where this sentence starts."
                    ),
                ),
                (
                    "end_char",
                    models.IntegerField(
                        help_text="Character offset where this sentence ends."
                    ),
                ),
                (
                    "word_position",
                    models.IntegerField(
                        default=0,
                        help_text="Word offset of the sentence start. Sentences > 600 are excluded from host scanning.",
                    ),
                ),
                (
                    "embedding",
                    VectorField(
                        blank=True,
                        dimensions=384,
                        help_text="384-dimension per-sentence embedding.",
                        null=True,
                    ),
                ),
                (
                    "content_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sentences",
                        to="content.contentitem",
                        help_text="The content item this sentence belongs to.",
                    ),
                ),
                (
                    "post",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="sentences",
                        to="content.post",
                        help_text="The post this sentence was extracted from.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Sentence",
                "verbose_name_plural": "Sentences",
                "unique_together": {("post", "position")},
            },
        ),
        migrations.AddIndex(
            model_name="sentence",
            index=models.Index(
                fields=["content_item", "position"], name="content_sentence_ci_pos_idx"
            ),
        ),
        migrations.AddIndex(
            model_name="sentence",
            index=models.Index(
                fields=["word_position"], name="content_sentence_word_pos_idx"
            ),
        ),
        migrations.CreateModel(
            name="ContentMetricSnapshot",
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
                    "import_job_id",
                    models.CharField(
                        help_text="Celery task ID of the import job.", max_length=100
                    ),
                ),
                (
                    "captured_at",
                    models.DateTimeField(help_text="When this snapshot was captured."),
                ),
                (
                    "view_count",
                    models.IntegerField(
                        default=0, help_text="View count at snapshot time."
                    ),
                ),
                (
                    "reply_count",
                    models.IntegerField(
                        default=0, help_text="Reply count at snapshot time."
                    ),
                ),
                (
                    "download_count",
                    models.IntegerField(
                        default=0, help_text="Download count at snapshot time."
                    ),
                ),
                (
                    "is_deleted",
                    models.BooleanField(
                        default=False,
                        help_text="Whether the content was deleted at snapshot time.",
                    ),
                ),
                (
                    "content_item",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="metric_snapshots",
                        to="content.contentitem",
                        help_text="The content item this snapshot belongs to.",
                    ),
                ),
            ],
            options={
                "verbose_name": "Content Metric Snapshot",
                "verbose_name_plural": "Content Metric Snapshots",
                "unique_together": {("import_job_id", "content_item")},
            },
        ),
        migrations.AddIndex(
            model_name="contentmetricsnapshot",
            index=models.Index(
                fields=["content_item", "captured_at"], name="content_cms_ci_date_idx"
            ),
        ),
    ]
