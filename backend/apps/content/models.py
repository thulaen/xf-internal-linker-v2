"""
Content models — XenForo threads, resources, posts, and sentences.

ContentItem is the core entity: anything that can be a link destination or host.
pgvector VectorField stores semantic embeddings for the currently active model.
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

    The embedding column stores the current model's vector and is tagged by
    embedding_model_version so future model swaps can coexist safely.
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
        db_index=True,
        help_text=(
            "SHA-256 hash of the raw post body, used to detect edits AND to "
            "find cross-source duplicates (Group A.6). Indexed so the dedup "
            "lookup at import time is O(log N), not a full table scan."
        ),
    )
    # Stage 10 — Content identity and deduplication
    source_key = models.CharField(
        max_length=200,
        blank=True,
        db_index=True,
        help_text="Stable compound key: source:object_type:remote_id (e.g. xenforo:thread:123).",
    )
    # Group A.6 — cross-source content deduplication. When the same article
    # is imported from both XenForo (forum thread) and WordPress (blog post),
    # ``duplicate_of`` points the second copy at the first one's row instead
    # of regenerating the embedding. Saves ~10–20 % of embedding compute on
    # dual-source sites and prevents one piece of content from showing up as
    # two separate ranking targets in the suggestion graph.
    duplicate_of = models.ForeignKey(
        "self",
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="duplicates",
        db_index=True,
        help_text=(
            "If set, this row was detected as a content duplicate of the "
            "linked ContentItem during import (matching content_hash). "
            "Embedding generation skips rows where this is set — they reuse "
            "the parent's embedding via this FK at retrieval time."
        ),
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
    # Group D.2 — SHA-256 of the exact text we last fed BGE-M3 for this
    # row. Combined with ``embedding_model_version``, lets the embed
    # generator skip rows whose text AND model both still match — no
    # duplicate embedding row ever gets written for unchanged content.
    # Plain English: "if nothing has changed about this post, don't
    # re-embed it." Saves GPU + disk on every recurring import.
    embedding_text_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=(
            "SHA-256 hex digest of the exact text passed to the embedding model "
            "(title + body + truncation). Re-embed fires whenever this hash drifts "
            "OR the model signature drifts. NULL/blank means the row has never been "
            "embedded under the new hash discipline (Group D.2) — treated as 'must "
            "re-embed' on next pass."
        ),
    )
    # Group D.4 — fraction of the raw post body that lived inside
    # ``[QUOTE]`` blocks before stripping. Captured at import time
    # (text_cleaner.compute_quotation_density). 0.0 = entirely original;
    # 1.0 = entirely quoted-from-elsewhere. Store-only signal; FR-041
    # Originality Provenance Scoring (pending) consumes it.
    quotation_density = models.FloatField(
        default=0.0,
        help_text=(
            "Quotation density (Group D.4) — quoted_chars / total_chars from "
            "the raw post body before BBCode stripping. Future input to "
            "FR-041 originality scoring; not used in ranking today."
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
    # Tier 2 slice 5 — per-term decomposition of the two composite scores for
    # operator visibility in the suggestion-detail dialog. JSON shape:
    # {"raw": float, "normalized": float, "terms": [{"name", "value", "weight",
    # "contribution"}]}. Empty dict when the destination has no telemetry.
    content_value_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Tier 2 slice 5 — per-term breakdown of compute_content_value_raw "
            "captured during _refresh_content_value_scores so the suggestion-"
            "detail dialog can show operators exactly which signal drove the "
            "composite. Kim et al. WSDM 2014 formula, not a new signal."
        ),
    )
    # Pick #26 — Gamon et al. 2013 entity salience scores. List of
    # ``{text, label, salience, mention_count}`` dicts for the top-K
    # most central named entities in the post body, populated at
    # import time from the spaCy NER + sentence-splitter Doc.
    # Empty list = unscored (cold-start row, body without named
    # entities, or import predates the wiring).
    salient_entities = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Top-K named entities by Gamon et al. 2013 salience score "
            "(0.0-1.0). Each entry: {text, label, salience, "
            "mention_count}. Populated by the importer's NER pass. "
            "Empty list = no entities or unscored row."
        ),
    )
    # Pick #25 — Callan 1994 passage-level segmentation. Sentence-
    # aligned ~150-token windows derived from the existing Sentence
    # rows during import. Each entry: ``{index, text, token_count,
    # token_start, token_end}``. Empty list = unscored (cold-start
    # row or empty body). Used by future passage-level retrieval
    # paths; produced now so the data is available for opt-in
    # consumers.
    passages = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Sentence-aligned passages (Callan 1994 fixed-window with "
            "overlap, ~150 tokens). Each entry: {index, text, "
            "token_count, token_start, token_end}. Populated at import "
            "from the same Sentence rows used for retrieval — no "
            "duplicate splitting work."
        ),
    )
    # Pick #35 — Elo rating (Elo 1978; default 1500 per chess
    # convention). Updated by the ``elo_rating_refresh`` scheduled
    # job from operator review-queue history; consumed at suggestion
    # write time as a per-destination quality signal.
    # Cold-start: every row has 1500 until the first Elo refresh
    # runs and finds approve/reject pairs.
    elo_rating = models.FloatField(
        default=1500.0,
        db_index=True,
        help_text=(
            "Elo rating (Elo 1978) updated from operator approve / "
            "reject pairs sharing the same host sentence. 1500 = "
            "no information yet (chess convention)."
        ),
    )
    engagement_quality_diagnostics = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Tier 2 slice 5 — per-term breakdown of _compute_engagement_raw_"
            "score captured during _refresh_engagement_quality_scores. Same "
            "shape as content_value_diagnostics."
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

    # pgvector embedding for the active model/runtime signature
    embedding = VectorField(
        null=True,
        blank=True,
        help_text="Semantic embedding for the active model. Pair with embedding_model_version when reading.",
    )

    # FR-105 — Reverse Search-Query Vocabulary Alignment (RSQVA) input.
    # TF-IDF vector over this page's GSC query vocabulary, L2-normalized
    # per Salton & Buckley 1988. Rebuilt daily by the
    # analytics.tasks.refresh_gsc_query_tfidf Celery Beat task. Null until
    # first sync. Stored as a pgvector so pair-cosine uses pgvector's <=>
    # operator at query time. Dimension is bounded by rsqva.max_vocab_size
    # (default 10000) via hashing.
    gsc_query_tfidf_vector = VectorField(
        null=True,
        blank=True,
        dimensions=1024,
        help_text="FR-105 RSQVA: L2-normalized TF-IDF vector over this page's GSC query vocabulary, projected to 1024-dim via feature hashing. Null until first analytics sync.",
    )

    # Pick #20 Product Quantization — compressed BGE-M3 embedding.
    # 1024-dim float32 (4 KB) → m subvectors × 1 byte each (8 bytes
    # default, configurable per the trained codebook). Populated by
    # the monthly product_quantization_refit scheduled job; null
    # until the first refit lands. Pair with the persisted codebook
    # in AppSetting["product_quantization.codebook"] when decoding.
    # See apps.sources.product_quantization for the FAISS wrapper
    # and apps.pipeline.services.product_quantization_producer for
    # the producer/backfill.
    char_ngram_vector = VectorField(
        null=True,
        blank=True,
        dimensions=256,
        help_text="Pick #58: 256-dim hashed character n-gram (3-5) vector. Null until first NLP enrichment pass.",
    )

    pq_code = models.BinaryField(
        null=True,
        blank=True,
        editable=False,
        help_text=(
            "Pick #20: PQ-compressed embedding (~8 bytes). Null until "
            "the first product_quantization_refit run encodes it. "
            "Decode via apps.pipeline.services.product_quantization_producer."
        ),
    )
    pq_code_version = models.CharField(
        max_length=64,
        null=True,
        blank=True,
        help_text=(
            "Codebook version that produced pq_code. Re-encoded on "
            "every refit; consumers must reject codes whose version "
            "doesn't match the active codebook."
        ),
    )

    # Picks #53, #54, #55 — NLP Enrichment Metadata.
    # Stores acronyms, lemmas, and noun-chunks extracted by the
    # NLPEnricher service during import.
    # Shape: {"lemmas": [], "noun_chunks": [], "acronyms": {}}
    nlp_metadata = models.JSONField(
        default=dict,
        blank=True,
        help_text=(
            "Group G (Harmonious-12) — NLP enrichment metadata including "
            "acronyms (Schwartz-Hearst 2003), lemmas, and noun-chunks. "
            "Populated at import time for downstream anchor matching."
        ),
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
    # Pick #19 — Flesch-Kincaid + Gunning Fog readability grades.
    # Computed at import time from clean_text via
    # apps.sources.readability.score so the ranker (and operators
    # browsing posts) can distinguish a graduate-level dissertation
    # (Fog ~20) from a conversational reply (Fog ~8) without re-
    # tokenising on every pipeline run. 0.0 = unscored (fresh row,
    # zero-length body, or import predates the wiring).
    flesch_kincaid_grade = models.FloatField(
        default=0.0,
        help_text=(
            "Flesch-Kincaid Grade Level (Kincaid et al. 1975). Higher = "
            "more reading skill required. Computed from clean_text at "
            "import time. 0.0 = unscored."
        ),
    )
    gunning_fog_grade = models.FloatField(
        default=0.0,
        help_text=(
            "Gunning Fog Index (Gunning 1952). Higher = more complex "
            "vocabulary. Computed from clean_text at import time. "
            "0.0 = unscored."
        ),
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
    The embedding column stores the current model's vector for per-sentence similarity.
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
    embedding_model_version = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=(
            "Model + preprocessing version that produced the current sentence embedding. "
            "Used to keep stage-2 similarity aligned with the active embedding model."
        ),
    )

    # pgvector per-sentence embedding for the active model/runtime signature
    embedding = VectorField(
        null=True,
        blank=True,
        help_text="Sentence embedding for the active model. Used in stage-2 similarity ranking.",
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


class Token(models.Model):
    """
    Granular token information extracted from a Sentence via spaCy.

    Pick #54 — stores the lemma for every word to enable high-accuracy
    anchor matching and lexical overlap scoring.
    """

    sentence = models.ForeignKey(
        Sentence,
        on_delete=models.CASCADE,
        related_name="tokens",
        help_text="The sentence this token belongs to.",
    )
    text = models.CharField(
        max_length=255,
        help_text="The literal token text.",
    )
    lemma = models.CharField(
        max_length=255,
        db_index=True,
        help_text="The base form of the word (token.lemma_).",
    )
    pos = models.CharField(
        max_length=16,
        db_index=True,
        help_text="The Part-of-Speech tag (token.pos_).",
    )
    is_stop = models.BooleanField(
        default=False,
        help_text="True if this token is a standard English stopword.",
    )
    start_char = models.IntegerField(
        help_text="Start offset within the sentence.",
    )
    end_char = models.IntegerField(
        help_text="End offset within the sentence.",
    )

    class Meta:
        verbose_name = "Token"
        verbose_name_plural = "Tokens"
        indexes = [
            models.Index(fields=["lemma", "pos"]),
        ]

    def __str__(self) -> str:
        return f"{self.text} -> {self.lemma} ({self.pos})"


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

    Disk footprint: vector bytes scale with the active model dimension. At
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
        null=True,
        blank=True,
        help_text="The old embedding vector that was replaced.",
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


class PassageEmbedding(models.Model):
    """One row per (ContentItem × passage) — masterplan Group E / FR-053.

    Plain-English: long pages have one perfectly-relevant section buried
    among less-relevant filler. The page-level embedding averages that
    section away. ``PassageEmbedding`` stores ~200-token slices of the
    page body so the ranker can compare a host sentence to the
    BEST-matching passage instead of the whole page.

    Storage shape: pgvector(1024) per passage, K passages per page
    (default 5), L2-normalised. At 100k pages that's ~2 GB on disk —
    within the 59 GB free-disk budget. Future optimisation
    (``passage_relevance.index_quantised``) replaces this with an
    int8-quantised FAISS index; the float32 pgvector path is V1.

    No-pile-up discipline (Group A.6 / D.2 / S):
      * ``embedding_text_hash`` is the SHA-256 of the chunked passage
        text. Re-embed only fires when this hash drifts.
      * Existing rows for a ContentItem are deleted + recreated when
        the page's content_hash changes (chunking is content-derived;
        partial updates would race).
      * Cross-source duplicates (Group A.6) reuse the canonical's
        passage embeddings via ``ContentItem.duplicate_of`` — no
        passages are stored on duplicate rows.
    """

    content_item = models.ForeignKey(
        ContentItem,
        on_delete=models.CASCADE,
        related_name="passage_embeddings",
        help_text="The page this passage was extracted from.",
    )
    passage_index = models.SmallIntegerField(
        help_text=(
            "Zero-based ordinal of the passage inside the page (0 = first, "
            "1 = next, ...). Used for diagnostics like 'best_passage_index'."
        ),
    )
    text = models.TextField(
        help_text=(
            "The passage text after chunking. Stored as plain text so the "
            "best-passage diagnostic preview can show the matching paragraph "
            "directly to operators in the suggestion-detail UI."
        ),
    )
    word_count = models.IntegerField(
        default=0,
        help_text="Number of whitespace-tokenised words in the passage.",
    )
    embedding = VectorField(
        null=True,
        blank=True,
        help_text=(
            "L2-normalised 1024-dim BGE-M3 embedding of the passage. NULL "
            "until the embedding pass touches this row; ranker treats NULL "
            "as the neutral fallback (no passage similarity contribution)."
        ),
    )
    embedding_model_version = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=(
            "Model + preprocessing version that produced the embedding. "
            "Used by the embed pass to skip rows already at the current "
            "signature (matches ContentItem / Sentence convention)."
        ),
    )
    embedding_text_hash = models.CharField(
        max_length=64,
        blank=True,
        db_index=True,
        help_text=(
            "SHA-256 of the exact passage text passed to the model. "
            "Re-embed fires when this hash drifts even if the model "
            "signature is unchanged."
        ),
    )
    passage_words_setting = models.SmallIntegerField(
        default=200,
        help_text=(
            "Value of `passage_relevance.passage_words` at chunk time. "
            "Used to detect when the chunking parameter has changed and "
            "the passages need to be regenerated."
        ),
    )
    opq_code = models.BinaryField(
        null=True,
        blank=True,
        help_text=(
            "M-dimensional byte array representing the quantised embedding. "
            "For M=64 subquantisers, this is exactly 64 bytes."
        ),
    )
    opq_codebook_version = models.CharField(
        max_length=40,
        blank=True,
        db_index=True,
        help_text=(
            "The `corpus_signature` of the OPQCodebook used to encode this passage. "
            "If the active codebook changes, the passage must be re-encoded."
        ),
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Passage Embedding"
        verbose_name_plural = "Passage Embeddings"
        ordering = ["content_item", "passage_index"]
        constraints = [
            models.UniqueConstraint(
                fields=["content_item", "passage_index"],
                name="unique_passage_per_content_item",
            ),
        ]
        indexes = [
            models.Index(fields=["content_item", "passage_index"]),
        ]

    def __str__(self) -> str:
        return (
            f"PassageEmbedding<content={self.content_item_id} "
            f"passage={self.passage_index} words={self.word_count}>"
        )


class OPQCodebook(models.Model):
    """Singleton model storing the trained Optimised Product Quantisation codebooks.

    Trained periodically by Celery (opq_trainer) and used by the C++ quantemb
    extension to encode embeddings into 64-byte codes and decode them back.
    Only one row is active at a time (is_active=True). Older rows are kept
    for fast rollback.
    """

    version = models.IntegerField(
        default=1,
        help_text="Format version for the codebook binaries.",
    )
    rotation = models.BinaryField(
        help_text="DxD float32 orthogonal rotation matrix applied before quantisation.",
    )
    codebooks = models.BinaryField(
        help_text="MxKxD_per_M float32 centroids for all subquantisers.",
    )
    n_subquantisers = models.IntegerField(
        help_text="M (number of subquantisers, e.g., 64). Each subquantiser produces 1 byte.",
    )
    k_centroids = models.IntegerField(
        help_text="K (centroids per subquantiser, almost always 256).",
    )
    corpus_signature = models.CharField(
        max_length=40,
        unique=True,
        help_text="Hash representing the passage corpus size/shape at training time.",
    )
    trained_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this codebook was trained.",
    )
    is_active = models.BooleanField(
        default=False,
        db_index=True,
        help_text="True for the single currently active codebook used for encoding.",
    )

    class Meta:
        verbose_name = "OPQ Codebook"
        verbose_name_plural = "OPQ Codebooks"
        ordering = ["-trained_at"]
        constraints = [
            models.UniqueConstraint(
                condition=models.Q(is_active=True),
                fields=["is_active"],
                name="single_active_opq_codebook",
            )
        ]

    def __str__(self) -> str:
        active_str = " (ACTIVE)" if self.is_active else ""
        return f"OPQCodebook<{self.corpus_signature}>{active_str}"
