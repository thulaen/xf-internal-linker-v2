"""
Content models — XenForo threads, resources, posts, and sentences.

ContentItem is the core entity: anything that can be a link destination or host.
pgvector VectorField stores 1024-dimension embeddings for semantic similarity search.
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
        ("wp_posts", "WordPress Posts"),
        ("wp_pages", "WordPress Pages"),
    ]

    scope_id = models.IntegerField(
        help_text="The ID of this node/category in XenForo or WordPress.",
    )
    scope_type = models.CharField(
        max_length=30,
        choices=SCOPE_TYPE_CHOICES,
        help_text="Whether this is a XenForo forum node, resource category, or WordPress scope.",
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


class ContentCluster(TimestampedModel):
    """
    Groups near-duplicate ContentItems (e.g. thread vs archive page).
    FR-014 implementation for canonicalization and suppression.
    """

    canonical_item = models.ForeignKey(
        "ContentItem",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="canonical_for_cluster",
        help_text="The preferred version of content in this cluster.",
    )
    is_manually_fixed = models.BooleanField(
        default=False,
        help_text="If True, auto-clustering will not override this cluster's members or canonical item.",
    )

    class Meta:
        verbose_name = "Content Cluster"
        verbose_name_plural = "Content Clusters"

    def __str__(self) -> str:
        return f"Cluster {self.pk} (Canonical: {self.canonical_item_id or 'None'})"


class ContentItem(TimestampedModel):
    """
    A single piece of indexable content: a XenForo thread, resource, or WordPress post.

    Each ContentItem can be both a DESTINATION (the page being linked to)
    and a HOST (the page that will contain a new link in one of its sentences).

    The embedding column stores a 1024-dimension vector from the
    BAAI/bge-m3 model, used for cosine similarity search via pgvector.
    """

    CONTENT_TYPE_CHOICES = [
        ("thread", "Forum Thread"),
        ("resource", "Resource"),
        ("wp_post", "WordPress Post"),
        ("wp_page", "WordPress Page"),
        ("crawled_page", "Crawled Page"),
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
        help_text="Whether this is a forum thread, resource, or WordPress content item.",
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
    # Stage 10 — Content identity and deduplication
    source_key = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        help_text="Stable compound key: source:object_type:remote_id (e.g. xenforo:thread:123).",
    )
    content_version = models.IntegerField(
        default=1,
        help_text="Monotonically increasing version number. Bumped when content_hash changes.",
    )
    canonical_url_history = models.JSONField(
        default=list,
        blank=True,
        help_text="History of URL/slug changes: [{url, changed_at}]. Never creates a new record on URL change.",
    )
    last_checked_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "Timestamp of the most recent re-import/recrawl touch, regardless of whether the content "
            "actually changed. Updated on every 'mark as checked' short-circuit (plan item 21) so "
            "operators can see that the item was verified without re-embedding."
        ),
    )
    embedding_model_version = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=(
            "Model + preprocessing version that produced the current embedding. Used by the "
            "superseded-embedding retention policy (plan item 20) to keep rollback copies "
            "when the model changes."
        ),
    )

    # ML scores
    march_2026_pagerank_score = models.FloatField(
        "March 2026 PageRank",
        default=0.0,
        db_index=True,
        help_text="March 2026 PageRank score based on edge prominence and context. Recalculated after each sync.",
    )
    velocity_score = models.FloatField(
        default=0.0,
        db_index=True,
        help_text="Recency/engagement velocity score. Higher = trending recently.",
    )
    link_freshness_score = models.FloatField(
        default=0.5,
        db_index=True,
        help_text="Link Freshness score based only on inbound link-history timing. 0.5 = neutral.",
    )
    content_value_score = models.FloatField(
        default=0.5,
        db_index=True,
        help_text=(
            "GA4 + Matomo + GSC composite score for linking value. 0.5 = "
            "neutral (no activity in the lookback window). Written by "
            "analytics.sync._refresh_content_value_scores via the pure "
            "formula compute_content_value_raw. Phase 3a/3c extension "
            "credits the dwell gradient (half-weight dwell-30s + full-weight "
            "dwell-60s) and penalises quick-exit rate per Kim et al. WSDM "
            "2014 — all three terms are zero when Phase 2 telemetry is "
            "unavailable, so pre-Phase 3a sites see no behaviour change."
        ),
    )
    engagement_quality_score = models.FloatField(
        default=0.5,
        db_index=True,
        help_text=(
            "GA4 engagement quality: 0.50*engaged_session_rate + "
            "0.30*normalized_avg_engagement_time + 0.20*inverse_bounce_rate. "
            "Phase 3b/3c extension adds bounded +0.025*dwell_30s_rate and "
            "+0.05*dwell_60s_rate credits and a -0.05*quick_exit_rate "
            "penalty (Kim et al. WSDM 2014). Final result clamped to "
            "[0.0, 1.0]. 0.5 = neutral (no data). Phase 2 terms are zero "
            "when their source columns are zero, so pre-Phase-2 sites see "
            "no behaviour change. Written by analytics sync layer."
        ),
    )
    click_distance_score = models.FloatField(
        default=0.5,
        db_index=True,
        help_text="Soft structural prior based on click distance and URL depth. 1.0 = shallow/prominent, 0.5 = neutral.",
    )

    # FR-040 — multimedia/engagement richness (0=sparse, 0.5=neutral, 1=rich)
    multimedia_coverage_score = models.FloatField(
        default=0.5,
        db_index=True,
        help_text=(
            "Multimedia richness: 0.4*video + 0.35*image_density + 0.25*alt_text_ratio. "
            "1.0 = optimal (video + images with alt text). 0.5 = neutral (text-only)."
        ),
    )
    # FR-042 — information density (0=filler, 0.5=balanced, 1=high-factual)
    fact_density_score = models.FloatField(
        default=0.5,
        db_index=True,
        help_text=(
            "Fact density: ratio of fact-like sentences minus filler penalty. "
            "Min 120 words required; below that = neutral 0.5."
        ),
    )
    # FR-044 — internal search demand (0=declining, 0.5=stable, 1=spike)
    search_intensity_score = models.FloatField(
        default=0.5,
        db_index=True,
        help_text=(
            "Recent (3-day) site-search impressions vs. 28-day baseline. "
            "Sigmoid: ratio 0.5x→0.2, 1.0x→0.5, 2.0x→0.8, 10x→1.0."
        ),
    )

    # FR-014 near-duplicate clustering
    cluster = models.ForeignKey(
        ContentCluster,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="members",
        help_text="The cluster this item belongs to. Used to suppress near-duplicates.",
    )
    is_canonical = models.BooleanField(
        default=False,
        db_index=True,
        help_text="Whether this is the preferred version for linking within its cluster.",
    )

    # pgvector embedding (1024 dims = BAAI/bge-m3)
    embedding = VectorField(
        dimensions=1024,
        null=True,
        blank=True,
        help_text="1024-dimension sentence embedding for semantic similarity search via pgvector.",
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
            models.Index(fields=["content_type", "march_2026_pagerank_score"]),
            models.Index(fields=["content_type", "velocity_score"]),
            models.Index(fields=["content_type", "link_freshness_score"]),
            models.Index(fields=["content_type", "content_value_score"]),
            models.Index(fields=["content_type", "click_distance_score"]),
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
        help_text="Word count of clean_text. Pipeline scans first HOST_SCAN_WORD_LIMIT words only.",
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
    The pipeline scans only sentences within the HOST_SCAN_WORD_LIMIT.
    The embedding column stores a 1024-dimension vector for per-sentence similarity.
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
        "Sentences with word_position > HOST_SCAN_WORD_LIMIT are excluded from host scanning.",
    )

    # pgvector per-sentence embedding (1024 dims = BAAI/bge-m3)
    embedding = VectorField(
        dimensions=1024,
        null=True,
        blank=True,
        help_text="1024-dimension sentence embedding. Used in stage-2 similarity ranking.",
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


class SupersededEmbedding(models.Model):
    """Archive of replaced embeddings (plan item 20).

    When a ContentItem's embedding is overwritten (because the content hash
    changed, the model changed, or preprocessing rules changed), the old
    vector is archived here before the new one is written.  Retention policy:

      - Rows are eligible for pruning 7 days after ``superseded_at``.
      - The pruner only deletes rows whose replacement has been *verified*
        (``replacement_verified_at`` is non-null).  That stops us from
        throwing away rollback copies when the new embedding turns out to
        be bad before anyone notices.
      - Rows that are still within the 7-day window, or not yet verified,
        stay untouched even if disk pressure grows.  Old unverified copies
        are a feature, not a leak.

    Disk footprint: ~4 KB per 1024-dim float32 vector + row overhead. At
    typical sync volumes this is bounded by the 7-day retention; steady-state
    disk usage at 90 days is effectively zero because everything past 7 days
    that was verified has been pruned.
    """

    content_item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="superseded_embeddings",
        help_text="The content item whose embedding was replaced.",
    )
    embedding = VectorField(
        dimensions=1024,
        null=True,
        blank=True,
        help_text="The old 1024-dim vector that was replaced.",
    )
    embedding_model_version = models.CharField(
        max_length=64,
        blank=True,
        help_text="Model + preprocessing version that produced this archived vector.",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="Content hash at the time this embedding was produced.",
    )
    content_version = models.IntegerField(
        default=1,
        help_text="ContentItem.content_version at the time of archival.",
    )
    superseded_at = models.DateTimeField(
        auto_now_add=True,
        db_index=True,
        help_text="When this embedding was replaced.",
    )
    replacement_verified_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text=(
            "When the replacement was verified as correct. The retention pruner "
            "only deletes archived rows whose replacement has been verified."
        ),
    )

    class Meta:
        verbose_name = "Superseded Embedding"
        verbose_name_plural = "Superseded Embeddings"
        ordering = ["-superseded_at"]
        indexes = [
            models.Index(fields=["content_item", "-superseded_at"]),
            models.Index(fields=["superseded_at", "replacement_verified_at"]),
        ]

    def __str__(self) -> str:
        return f"SupersededEmbedding<content={self.content_item_id} superseded_at={self.superseded_at}>"
