"""
Crawler models — CrawlSession tracks crawl operations, CrawledPageMeta stores
per-page SEO metadata extracted during crawling, SitemapConfig stores user-
configured sitemap URLs, and SystemEvent powers the real-time activity feed.
"""

import uuid

from django.db import models

from apps.core.models import TimestampedModel


# ---------------------------------------------------------------------------
# CrawlSession — one crawl run (start -> pause/complete/fail)
# ---------------------------------------------------------------------------
class CrawlSession(TimestampedModel):
    """
    Tracks a single crawl session lifecycle.

    Sessions are triggered by the user from the GUI (never automatic).
    They checkpoint to Redis every 100 pages for crash-resilient resume.
    """

    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("paused", "Paused"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    session_id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    site_domain = models.CharField(
        max_length=255,
        help_text="Domain being crawled (e.g. 'goldmidi.com').",
    )

    # ── Configuration snapshot (frozen at start) ─────────────────────
    config = models.JSONField(
        default=dict,
        help_text=(
            "Crawl settings frozen at start: rate_limit, max_depth, "
            "max_pages, excluded_paths, timeout_hours."
        ),
    )

    # ── Progress counters ────────────────────────────────────────────
    pages_crawled = models.IntegerField(default=0)
    pages_changed = models.IntegerField(
        default=0, help_text="Pages whose content differed from last crawl."
    )
    pages_skipped_304 = models.IntegerField(
        default=0, help_text="Pages that returned 304 Not Modified."
    )
    new_pages_discovered = models.IntegerField(
        default=0, help_text="Pages found that had no prior crawl record."
    )
    broken_links_found = models.IntegerField(default=0)
    bytes_downloaded = models.BigIntegerField(default=0)
    elapsed_seconds = models.FloatField(default=0.0)

    # ── Overall progress (0.0-1.0) for the progress bar ──────────────
    progress = models.FloatField(
        default=0.0, help_text="Overall crawl progress 0.0-1.0."
    )
    message = models.CharField(max_length=500, blank=True)

    # ── Checkpoint for resume ────────────────────────────────────────
    checkpoint_frontier_key = models.CharField(
        max_length=200,
        blank=True,
        help_text="Redis key holding the serialised URL frontier for resume.",
    )
    # Plan item 31 — exact-boundary resume.  Instead of only pointing at a
    # Redis key (volatile), also persist a lightweight snapshot of the URL
    # frontier and the set of already-visited URL hashes to the DB so a
    # crash that also loses Redis can still resume from the right place.
    frontier_snapshot = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Durable snapshot of the URL queue at the last safe pause. "
            "Each entry is {url, depth}. Persisted to the DB so we can resume "
            "even if Redis has been flushed."
        ),
    )
    visited_hashes = models.JSONField(
        default=list,
        blank=True,
        help_text=(
            "Stable hashes of URLs already crawled in this session. Prevents "
            "re-visiting on resume."
        ),
    )
    scan_version = models.IntegerField(
        default=1,
        help_text=(
            "Monotonic counter incremented each time the crawl definition changes. "
            "Resume uses this to refuse mixing snapshots across versions."
        ),
    )
    is_resumable = models.BooleanField(default=False)

    # ── Error details ────────────────────────────────────────────────
    error_message = models.TextField(blank=True)

    # ── Timestamps ───────────────────────────────────────────────────
    started_at = models.DateTimeField(null=True, blank=True)
    paused_at = models.DateTimeField(null=True, blank=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Crawl Session"
        verbose_name_plural = "Crawl Sessions"

    def __str__(self) -> str:
        return (
            f"Crawl {self.site_domain} [{self.status}] {self.created_at:%Y-%m-%d %H:%M}"
        )


# ---------------------------------------------------------------------------
# CrawledPageMeta — per-page SEO metadata
# ---------------------------------------------------------------------------
class CrawledPageMeta(TimestampedModel):
    """
    SEO metadata extracted from a single crawled page.

    Stored separately from ContentItem so crawler data never overwrites
    authoritative API-imported content.  Linked to ContentItem by URL when
    a match exists.
    """

    url = models.URLField(
        max_length=2000, db_index=True, help_text="Canonical URL of the page."
    )
    normalized_url = models.CharField(
        max_length=2000,
        db_index=True,
        help_text="URL after normalisation (lowercase host, strip fragment/trailing slash).",
    )

    # ── Link to the crawl session that produced this record ──────────
    session = models.ForeignKey(
        CrawlSession,
        on_delete=models.CASCADE,
        related_name="pages",
    )
    # Optional FK to ContentItem when URL matches an API-imported page.
    content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="crawled_meta",
    )

    # ── HTTP response info ───────────────────────────────────────────
    http_status = models.SmallIntegerField(
        default=200, help_text="HTTP response status code."
    )
    response_time_ms = models.IntegerField(
        default=0, help_text="Time to first byte in milliseconds."
    )
    redirect_chain = models.JSONField(
        default=list,
        help_text="List of (url, status) tuples if page redirected.",
    )
    content_type = models.CharField(max_length=100, blank=True)
    content_length = models.IntegerField(
        default=0, help_text="Response body size in bytes."
    )

    # ── SEO tags ─────────────────────────────────────────────────────
    title = models.CharField(max_length=500, blank=True)
    meta_description = models.TextField(blank=True)
    canonical_url = models.URLField(max_length=2000, blank=True)
    robots_meta = models.CharField(
        max_length=200,
        blank=True,
        help_text="Content of <meta name='robots'> tag.",
    )
    has_viewport = models.BooleanField(
        default=False, help_text="True if <meta name='viewport'> is present."
    )

    # ── Headings ─────────────────────────────────────────────────────
    h1_text = models.CharField(
        max_length=500, blank=True, help_text="Text of the first <h1> tag."
    )
    h1_count = models.SmallIntegerField(
        default=0, help_text="Number of <h1> tags on the page."
    )
    heading_structure = models.JSONField(
        default=list,
        help_text="Ordered list of {'level': 1-6, 'text': '...'} for H1-H6.",
    )

    # ── Open Graph ───────────────────────────────────────────────────
    og_title = models.CharField(max_length=500, blank=True)
    og_description = models.TextField(blank=True)

    # ── Structured data ──────────────────────────────────────────────
    structured_data_types = models.JSONField(
        default=list,
        help_text="List of Schema.org @type values found in JSON-LD blocks.",
    )

    # ── Content metrics ──────────────────────────────────────────────
    word_count = models.IntegerField(
        default=0, help_text="Word count of extracted main content."
    )
    extracted_text = models.TextField(
        blank=True,
        help_text="Clean text extracted from main content area (no HTML).",
    )
    content_hash = models.CharField(
        max_length=64,
        blank=True,
        help_text="SHA-256 of extracted_text for change detection.",
    )
    content_to_html_ratio = models.FloatField(
        default=0.0,
        help_text="len(extracted_text) / len(raw_html). Low = boilerplate-heavy.",
    )

    # ── Image audit ──────────────────────────────────────────────────
    img_total = models.IntegerField(default=0)
    img_missing_alt = models.IntegerField(
        default=0, help_text="Images without alt attribute."
    )

    # ── Internal links found on this page ────────────────────────────
    internal_link_count = models.IntegerField(default=0)
    external_link_count = models.IntegerField(default=0)
    nofollow_link_count = models.IntegerField(default=0)

    # ── Crawl depth ──────────────────────────────────────────────────
    crawl_depth = models.SmallIntegerField(
        default=0, help_text="Minimum click distance from homepage."
    )

    # ── Change tracking ──────────────────────────────────────────────
    etag = models.CharField(
        max_length=200,
        blank=True,
        help_text="ETag header from last crawl (for conditional re-crawl).",
    )
    last_modified = models.CharField(
        max_length=200,
        blank=True,
        help_text="Last-Modified header from last crawl.",
    )
    consecutive_404_count = models.SmallIntegerField(
        default=0,
        help_text="Times this URL returned 404 in consecutive crawls. Auto-prune at 3.",
    )

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Crawled Page Metadata"
        verbose_name_plural = "Crawled Page Metadata"
        indexes = [
            models.Index(fields=["session", "http_status"]),
            models.Index(fields=["word_count"]),
            models.Index(fields=["consecutive_404_count"]),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["session", "normalized_url"],
                name="unique_page_per_session",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.url} [{self.http_status}] ({self.word_count} words)"


# ---------------------------------------------------------------------------
# CrawledLink — internal links discovered during crawl
# ---------------------------------------------------------------------------
class CrawledLink(TimestampedModel):
    """
    An internal link discovered on a crawled page.

    Stored separately from ExistingLink so crawler data does not collide
    with API-imported link data.  Merged into ExistingLink during pipeline.
    """

    page = models.ForeignKey(
        CrawledPageMeta,
        on_delete=models.CASCADE,
        related_name="links",
    )
    destination_url = models.URLField(max_length=2000)
    anchor_text = models.TextField(blank=True)

    CONTEXT_CHOICES = [
        ("content", "Main Content"),
        ("nav", "Navigation"),
        ("sidebar", "Sidebar"),
        ("footer", "Footer"),
        ("breadcrumb", "Breadcrumb"),
        ("unknown", "Unknown"),
    ]
    context_class = models.CharField(
        max_length=20,
        choices=CONTEXT_CHOICES,
        default="content",
        help_text="Where on the page this link was found.",
    )
    is_nofollow = models.BooleanField(default=False)

    class Meta:
        verbose_name = "Crawled Link"
        verbose_name_plural = "Crawled Links"

    def __str__(self) -> str:
        return f"{self.anchor_text[:50]} -> {self.destination_url[:80]}"


# ---------------------------------------------------------------------------
# SitemapConfig — user-configured sitemap URLs
# ---------------------------------------------------------------------------
class SitemapConfig(TimestampedModel):
    """
    A sitemap URL configured by the user for a specific domain.

    Supports both manual entry and auto-discovery.  Normalised URL is
    used for dedup so the same sitemap is never added twice.
    """

    DISCOVERY_CHOICES = [
        ("manual", "Manual"),
        ("auto", "Auto-discovered"),
    ]

    domain = models.CharField(
        max_length=255,
        db_index=True,
        help_text="Domain this sitemap belongs to (e.g. 'goldmidi.com').",
    )
    sitemap_url = models.URLField(
        max_length=2000,
        help_text="Full URL of the sitemap (e.g. 'https://goldmidi.com/community/sitemap.php').",
    )
    normalized_url = models.CharField(
        max_length=2000,
        unique=True,
        help_text="Normalised URL for dedup (lowercase, no trailing slash).",
    )
    discovery_method = models.CharField(
        max_length=20, choices=DISCOVERY_CHOICES, default="manual"
    )
    is_enabled = models.BooleanField(
        default=True, help_text="Disabled sitemaps are skipped during crawl."
    )

    # ── Last fetch metadata ──────────────────────────────────────────
    last_fetch_at = models.DateTimeField(null=True, blank=True)
    last_url_count = models.IntegerField(
        default=0, help_text="Number of URLs found in last fetch."
    )
    last_error = models.TextField(blank=True)

    class Meta:
        ordering = ["domain", "sitemap_url"]
        verbose_name = "Sitemap Configuration"
        verbose_name_plural = "Sitemap Configurations"

    def __str__(self) -> str:
        status = "enabled" if self.is_enabled else "disabled"
        return f"{self.domain}: {self.sitemap_url} ({status})"


# ---------------------------------------------------------------------------
# SystemEvent — activity feed events for the real-time Dashboard timeline
# ---------------------------------------------------------------------------
class SystemEvent(models.Model):
    """
    A single event in the system activity feed.

    Events are emitted by heartbeat tasks, Celery completions, webhook
    receivers, and health checks.  Auto-pruned every 4 weeks.
    """

    SEVERITY_CHOICES = [
        ("info", "Info"),
        ("success", "Success"),
        ("warning", "Warning"),
        ("error", "Error"),
    ]

    SOURCE_CHOICES = [
        ("heartbeat", "Heartbeat"),
        ("sync", "Sync"),
        ("crawler", "Crawler"),
        ("pipeline", "Pipeline"),
        ("health", "Health Check"),
        ("webhook", "Webhook"),
        ("prune", "Auto-Prune"),
        ("model", "ML Model"),
        ("system", "System"),
    ]

    event_id = models.UUIDField(default=uuid.uuid4, primary_key=True, editable=False)
    severity = models.CharField(
        max_length=10, choices=SEVERITY_CHOICES, default="info", db_index=True
    )
    source = models.CharField(
        max_length=20, choices=SOURCE_CHOICES, default="system", db_index=True
    )
    title = models.CharField(
        max_length=200,
        help_text="One-line plain-English description of what happened.",
    )
    detail = models.TextField(
        blank=True,
        help_text="Optional extra context (item counts, duration, etc.).",
    )
    metadata = models.JSONField(
        default=dict,
        help_text="Structured data for the event (e.g. items_count, duration_ms).",
    )
    timestamp = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        ordering = ["-timestamp"]
        verbose_name = "System Event"
        verbose_name_plural = "System Events"
        indexes = [
            models.Index(fields=["-timestamp", "severity"]),
            models.Index(fields=["source", "-timestamp"]),
        ]

    def __str__(self) -> str:
        return f"[{self.severity}] {self.title} ({self.timestamp:%H:%M})"
