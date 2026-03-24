"""
Content models — XenForo threads, resources, posts, and sentences.

ContentItem is the core entity: anything that can be a link destination or host.
pgvector VectorField stores 384-dimension embeddings for semantic similarity search.
"""

from django.db import models
from pgvector.django import VectorField

from apps.core.models import TimestampedModel


class SiloGroup(TimestampedModel):
    """A topical silo that can be assigned to one or more scopes."""

    name = models.CharField(
        max_length=200,
        unique=True,
        help_text="Human-readable silo label shown in settings and review UI.",
    )
    slug = models.SlugField(
        max_length=200,
        unique=True,
        help_text="Stable machine-friendly identifier for this silo group.",
    )
    description = models.TextField(
        blank=True,
        help_text="Optional notes describing what belongs in this silo.",
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Sort order for silo management screens.",
    )

    class Meta:
        verbose_name = "Silo Group"
        verbose_name_plural = "Silo Groups"
        ordering = ["display_order", "name"]
        indexes = [
            models.Index(fields=["display_order", "name"]),
        ]

    def __str__(self) -> str:
        return self.name


class ScopeItem(TimestampedModel):
    """
    A XenForo forum node or resource category that groups content.
    Used to filter which threads/resources are included in pipeline runs.
    """

    SCOPE_TYPE_CHOICES = [
        ("node", "Forum Node"),
        ("resource_category", "Resource Category"),
        ("wp_category", "WordPress Category"),
    ]

    scope_id = models.IntegerField(
        help_text="The ID of this node/category in XenForo or WordPress.",
    )
    scope_type = models.CharField(
        max_length=30,
        choices=SCOPE_TYPE_CHOICES,
        help_text="Whether this is a XenForo forum node, resource category, or WP category.",
    )
    title = models.CharField(
        max_length=500,
        help_text="Display name of the node or category.",
    )
    parent = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="children",
        help_text="Parent scope item (e.g. a sub-forum's parent forum).",
    )
    silo_group = models.ForeignKey(
        SiloGroup,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="scope_items",
        help_text="Optional topical silo assignment used by the ranking pipeline.",
    )
    is_enabled = models.BooleanField(
        default=True,
        help_text="Only enabled scopes are included in pipeline runs.",
    )
    content_count = models.IntegerField(
        default=0,
        help_text="Cached count of content items in this scope.",
    )
    display_order = models.IntegerField(
        default=0,
        help_text="Sort order for display in the UI.",
    )
    metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text="Extra data from the XenForo API response (stored for reference).",
    )

    class Meta:
        verbose_name = "Scope Item"
        verbose_name_plural = "Scope Items"
        unique_together = [["scope_id", "scope_type"]]
        indexes = [
            models.Index(fields=["scope_type", "is_enabled"]),
            models.Index(fields=["silo_group", "is_enabled"]),
        ]

    def __str__(self) -> str:
        return f"{self.title} [{self.scope_type}:{self.scope_id}]"


class ContentItem(TimestampedModel):
    """
    A single piece of indexable content: a XenForo thread, resource, or WordPress post.

    Each ContentItem can be both a DESTINATION (the page being linked to)
    and a HOST (the page that will contain a new link in one of its sentences).

    The embedding column stores a 384-dimension vector from the sentence-transformers
    model, used for cosine similarity search via pgvector.
    """

    CONTENT_TYPE_CHOICES = [
        ("thread", "Forum Thread"),
        ("resource", "Resource"),
        ("wp_post", "WordPress Post"),
    ]

    DISTILL_METHOD_CHOICES = [
        ("title_plus_body", "Title + Body"),
        ("title_only", "Title Only"),
    ]

    content_id = models.IntegerField(
        help_text="The original ID in XenForo or WordPress (not the local DB primary key).",
    )
    content_type = models.CharField(
        max_length=30,
        choices=CONTENT_TYPE_CHOICES,
        help_text="Whether this is a forum thread, resource, or WordPress post.",
    )
    title = models.CharField(
        max_length=500,
        help_text="The title of the thread or resource.",
    )
    url = models.URLField(
        max_length=1000,
        blank=True,
        help_text="Canonical URL of this content on the live forum.",
    )
    scope = models.ForeignKey(
        ScopeItem,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="content_items",
        help_text="The forum node or category this content belongs to.",
    )
    distilled_text = models.TextField(
        blank=True,
        help_text="Compact topical summary: title + most information-dense sentences. Used for embedding.",
    )
    distill_method = models.CharField(
        max_length=50,
        choices=DISTILL_METHOD_CHOICES,
        default="title_plus_body",
        help_text="How the distilled_text was generated.",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 hash of the raw post body, used to detect edits.",
    )

    # ML scores
    pagerank_score = models.FloatField(
        default=0.0,
        db_index=True,
        help_text="PageRank authority score (higher = more linked-to). Recalculated after each sync.",
    )
    velocity_score = models.FloatField(
        default=0.0,
        db_index=True,
        help_text="Recency/engagement velocity score. Higher = trending recently.",
    )

    # pgvector embedding (384 dims = all-MiniLM-L6-v2 / multi-qa-MiniLM-L6-cos-v1)
    embedding = VectorField(
        dimensions=384,
        null=True,
        blank=True,
        help_text="384-dimension sentence embedding for semantic similarity search via pgvector.",
    )

    # Engagement metrics (mirrored from XenForo)
    view_count = models.IntegerField(
        default=0,
        help_text="Number of views on the live forum.",
    )
    reply_count = models.IntegerField(
        default=0,
        help_text="Number of replies (threads) or reviews (resources).",
    )
    download_count = models.IntegerField(
        default=0,
        help_text="Download count for resources (0 for threads).",
    )

    # XenForo internal IDs
    xf_post_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="XenForo post ID of the first post (for edit detection).",
    )
    xf_update_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="XenForo update/version ID (used to detect edits without re-fetching body).",
    )

    post_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the thread/resource was originally posted.",
    )
    last_post_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the most recent reply was posted.",
    )
    is_deleted = models.BooleanField(
        default=False,
        help_text="True if this content was deleted on the live forum (suggestions become stale).",
    )
    fetched_at = models.DateTimeField(
        auto_now=True,
        help_text="Last time this record was synced from the XenForo API.",
    )

    class Meta:
        verbose_name = "Content Item"
        verbose_name_plural = "Content Items"
        unique_together = [["content_id", "content_type"]]
        indexes = [
            models.Index(fields=["content_type", "pagerank_score"]),
            models.Index(fields=["content_type", "velocity_score"]),
            models.Index(fields=["is_deleted"]),
        ]

    def __str__(self) -> str:
        return f"[{self.content_type}:{self.content_id}] {self.title[:80]}"


class Post(TimestampedModel):
    """
    The first post body of a ContentItem.

    Stores both the raw BBCode (as fetched from XenForo) and the cleaned
    plain text (for sentence splitting and word counting).
    One Post per ContentItem (OneToOne).
    """

    content_item = models.OneToOneField(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="post",
        help_text="The content item this post belongs to.",
    )
    raw_bbcode = models.TextField(
        help_text="Original BBCode from XenForo, unmodified.",
    )
    clean_text = models.TextField(
        blank=True,
        help_text="Plain text after stripping BBCode tags and URLs. Used for sentence splitting.",
    )
    char_count = models.IntegerField(
        default=0,
        help_text="Character count of clean_text.",
    )
    word_count = models.IntegerField(
        default=0,
        help_text="Word count of clean_text. Pipeline scans first 600 words only.",
    )
    xf_post_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="XenForo post ID (for direct API lookups).",
    )
    xf_update_id = models.IntegerField(
        null=True,
        blank=True,
        help_text="XenForo update ID (used to check if post was edited).",
    )
    last_edit_date = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When this post was last edited on the forum.",
    )

    class Meta:
        verbose_name = "Post"
        verbose_name_plural = "Posts"

    def __str__(self) -> str:
        return f"Post for {self.content_item}"


class Sentence(models.Model):
    """
    A single sentence extracted from a Post's clean_text via spaCy.

    Each sentence can be a candidate HOST for a link insertion.
    The pipeline scans only sentences within the first 600 words (word_position <= 600).
    The embedding column stores a 384-dimension vector for per-sentence similarity.
    """

    content_item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="sentences",
        help_text="The content item this sentence belongs to.",
    )
    post = models.ForeignKey(
        Post,
        on_delete=models.CASCADE,
        related_name="sentences",
        help_text="The post this sentence was extracted from.",
    )
    text = models.TextField(
        help_text="The sentence text as extracted by spaCy.",
    )
    position = models.IntegerField(
        help_text="Zero-based sentence index within the post.",
    )
    char_count = models.IntegerField(
        help_text="Character length of this sentence.",
    )
    start_char = models.IntegerField(
        help_text="Character offset where this sentence starts in clean_text.",
    )
    end_char = models.IntegerField(
        help_text="Character offset where this sentence ends in clean_text.",
    )
    word_position = models.IntegerField(
        default=0,
        help_text="Word offset of the sentence start in the post. "
                  "Sentences with word_position > 600 are excluded from host scanning.",
    )

    # pgvector per-sentence embedding
    embedding = VectorField(
        dimensions=384,
        null=True,
        blank=True,
        help_text="384-dimension sentence embedding. Used in stage-2 similarity ranking.",
    )

    class Meta:
        verbose_name = "Sentence"
        verbose_name_plural = "Sentences"
        unique_together = [["post", "position"]]
        indexes = [
            models.Index(fields=["content_item", "position"]),
            models.Index(fields=["word_position"]),
        ]

    def __str__(self) -> str:
        return f"[pos={self.position}] {self.text[:80]}"


class ContentMetricSnapshot(models.Model):
    """
    A point-in-time snapshot of engagement metrics for a ContentItem.
    Created on each import run so velocity scores can be computed by comparing
    recent vs. historical view/reply counts.
    """

    content_item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="metric_snapshots",
        help_text="The content item this snapshot belongs to.",
    )
    import_job_id = models.CharField(
        max_length=100,
        help_text="Celery task ID of the import job that created this snapshot.",
    )
    captured_at = models.DateTimeField(
        help_text="When this snapshot was captured.",
    )
    view_count = models.IntegerField(
        default=0,
        help_text="View count at snapshot time.",
    )
    reply_count = models.IntegerField(
        default=0,
        help_text="Reply count at snapshot time.",
    )
    download_count = models.IntegerField(
        default=0,
        help_text="Download count at snapshot time (resources only).",
    )
    is_deleted = models.BooleanField(
        default=False,
        help_text="Whether the content was deleted at snapshot time.",
    )

    class Meta:
        verbose_name = "Content Metric Snapshot"
        verbose_name_plural = "Content Metric Snapshots"
        unique_together = [["import_job_id", "content_item"]]
        indexes = [
            models.Index(fields=["content_item", "-captured_at"]),
        ]

    def __str__(self) -> str:
        return f"Snapshot {self.captured_at.date()} — {self.content_item}"
