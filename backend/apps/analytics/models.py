"""
Analytics models — GSC/GA4 search metrics and before/after impact reports.

SearchMetric stores daily performance data pulled from Google Search Console
and Google Analytics 4. ImpactReport compares metrics before vs. after a
suggestion was applied to measure real SEO impact.
"""

from django.db import models


class SearchMetric(models.Model):
    """
    A single day's GSC or GA4 performance data for a content item.

    Pulled periodically by the analytics Celery task (rate-limited).
    Used to compute before/after impact reports for applied suggestions.
    """

    SOURCE_CHOICES = [
        ("gsc", "Google Search Console"),
        ("ga4", "Google Analytics 4"),
    ]

    content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="search_metrics",
        help_text="The content item these metrics belong to.",
    )
    date = models.DateField(
        db_index=True,
        help_text="The date these metrics were recorded for.",
    )
    source = models.CharField(
        max_length=10,
        choices=SOURCE_CHOICES,
        help_text="Whether this data came from GSC or GA4.",
    )

    # GSC metrics
    impressions = models.IntegerField(
        default=0,
        help_text="Number of times this URL appeared in Google search results.",
    )
    clicks = models.IntegerField(
        default=0,
        help_text="Number of clicks from Google search results.",
    )
    ctr = models.FloatField(
        default=0.0,
        help_text="Click-through rate (clicks / impressions).",
    )
    average_position = models.FloatField(
        null=True,
        blank=True,
        help_text="Average ranking position in Google search (lower = better).",
    )
    query = models.CharField(
        max_length=500,
        blank=True,
        help_text="Top search query driving traffic to this URL (optional).",
    )

    # GA4 metrics
    page_views = models.IntegerField(
        default=0,
        help_text="Total page views from GA4.",
    )
    sessions = models.IntegerField(
        default=0,
        help_text="Total sessions from GA4.",
    )
    avg_engagement_time = models.FloatField(
        default=0.0,
        help_text="Average engagement time in seconds (GA4).",
    )
    bounce_rate = models.FloatField(
        null=True,
        blank=True,
        help_text="Bounce rate percentage (GA4).",
    )

    class Meta:
        verbose_name = "Search Metric"
        verbose_name_plural = "Search Metrics"
        unique_together = [["content_item", "date", "source", "query"]]
        indexes = [
            models.Index(fields=["date", "source"]),
            models.Index(fields=["content_item", "-date"]),
        ]

    def __str__(self) -> str:
        return f"[{self.source}] {self.content_item} on {self.date}"


class ImpactReport(models.Model):
    """
    Before/after performance comparison for an applied suggestion.

    Created after a suggestion is applied and enough time has passed to
    measure real GSC/GA4 impact. Compares a 'before' window to an 'after' window.
    """

    METRIC_TYPE_CHOICES = [
        ("impressions", "Impressions"),
        ("clicks", "Clicks"),
        ("position", "Average Position"),
        ("page_views", "Page Views"),
        ("sessions", "Sessions"),
        ("ctr", "Click-Through Rate"),
    ]

    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        on_delete=models.CASCADE,
        related_name="impact_reports",
        help_text="The applied suggestion this report measures.",
    )
    metric_type = models.CharField(
        max_length=30,
        choices=METRIC_TYPE_CHOICES,
        help_text="Which metric is being compared.",
    )
    before_value = models.FloatField(
        help_text="Average metric value in the 'before' date window.",
    )
    after_value = models.FloatField(
        help_text="Average metric value in the 'after' date window.",
    )
    before_date_range = models.JSONField(
        help_text="Date range for the 'before' window: {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}.",
    )
    after_date_range = models.JSONField(
        help_text="Date range for the 'after' window: {'start': 'YYYY-MM-DD', 'end': 'YYYY-MM-DD'}.",
    )
    delta_percent = models.FloatField(
        help_text="Percentage change: ((after - before) / before) * 100. Positive = improvement.",
    )
    control_pool_size = models.IntegerField(
        default=0,
        help_text="Number of candidate control items before similarity matching.",
    )
    control_match_count = models.IntegerField(
        default=0,
        help_text="Number of controls selected after similarity matching.",
    )
    control_match_quality = models.FloatField(
        null=True,
        blank=True,
        help_text="Average pre-period similarity score of selected controls (0-1).",
    )
    is_conclusive = models.BooleanField(
        default=True,
        help_text="False when insufficient controls or data make the result unreliable.",
    )
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this impact report was generated.",
    )

    class Meta:
        verbose_name = "Impact Report"
        verbose_name_plural = "Impact Reports"
        ordering = ["-created_at"]


class GSCKeywordImpact(models.Model):
    """
    Stores keyword-level lift for a specific applied suggestion.
    FR-017 implementation for query-level attribution.
    """

    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        on_delete=models.CASCADE,
        related_name="keyword_impacts",
        help_text="The suggestion this keyword lift is attributed to.",
    )
    query = models.CharField(
        max_length=500,
        help_text="The specific search query from GSC.",
    )
    clicks_baseline = models.IntegerField(default=0)
    clicks_post = models.IntegerField(default=0)
    impressions_baseline = models.IntegerField(default=0)
    impressions_post = models.IntegerField(default=0)
    position_baseline = models.FloatField(null=True, blank=True)
    position_post = models.FloatField(null=True, blank=True)
    lift_percent = models.FloatField(
        default=0.0,
        help_text="Percentage click lift (normalized).",
    )
    is_anchor_match = models.BooleanField(
        default=False,
        help_text="True if the query contains the suggestion's anchor text.",
    )

    class Meta:
        verbose_name = "GSC Keyword Impact"
        verbose_name_plural = "GSC Keyword Impacts"
        unique_together = [["suggestion", "query"]]
        ordering = ["-lift_percent", "-clicks_post"]
        indexes = [
            models.Index(fields=["suggestion", "lift_percent"]),
            models.Index(fields=["is_anchor_match"]),
        ]

    def __str__(self) -> str:
        return f"{self.query} (+{self.lift_percent:.1f}%) for {self.suggestion_id}"


class SuggestionTelemetryDaily(models.Model):
    """Daily FR-016 telemetry rollup for one suggestion or unattributed bucket."""

    TELEMETRY_SOURCE_CHOICES = [
        ("ga4", "Google Analytics 4"),
        ("matomo", "Matomo"),
    ]

    date = models.DateField(db_index=True)
    telemetry_source = models.CharField(
        max_length=20, choices=TELEMETRY_SOURCE_CHOICES, db_index=True
    )
    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        null=True,
        blank=True,
        on_delete=models.CASCADE,
        related_name="telemetry_rows",
    )
    destination = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="telemetry_as_destination",
    )
    host = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="telemetry_as_host",
    )
    algorithm_key = models.CharField(max_length=100, blank=True)
    algorithm_version_date = models.DateField(null=True, blank=True)
    algorithm_version_slug = models.CharField(max_length=100, blank=True)
    event_schema = models.CharField(max_length=50, default="fr016_v1")
    device_category = models.CharField(max_length=50, blank=True)
    default_channel_group = models.CharField(max_length=120, blank=True)
    source_medium = models.CharField(max_length=120, blank=True)
    country = models.CharField(max_length=120, blank=True)
    region = models.CharField(max_length=120, blank=True)
    source_label = models.CharField(max_length=50, blank=True)
    same_silo = models.BooleanField(null=True, blank=True)
    impressions = models.IntegerField(default=0)
    clicks = models.IntegerField(default=0)
    destination_views = models.IntegerField(default=0)
    engaged_sessions = models.IntegerField(default=0)
    conversions = models.IntegerField(default=0)
    sessions = models.IntegerField(default=0)
    bounce_sessions = models.IntegerField(default=0)
    # Phase 2 richer engagement signals (plans/what-is-other-telemetry-*).
    # Source: Kim, Hassan, White & Zitouni (2014) "Modeling dwell time to
    # predict click-level satisfaction" (WSDM) — dwell-tier and quick-exit
    # counts are stronger ranking signals than the single existing
    # `engaged_sessions` boolean. Dwell buckets at 30s/60s combine with the
    # existing 10s `engaged_sessions` to form a three-tier distribution.
    quick_exit_sessions = models.IntegerField(
        default=0,
        help_text=(
            "Count of sessions where the user left the destination page within "
            "5s of landing (suggestion_destination_quick_exit event). Strong "
            "negative signal — 'pogo-sticking' — a bad suggestion match."
        ),
    )
    dwell_30s_sessions = models.IntegerField(
        default=0,
        help_text=(
            "Count of sessions that stayed on the destination page for 30s+ "
            "(suggestion_destination_dwell_30s event). Intermediate positive "
            "signal."
        ),
    )
    dwell_60s_sessions = models.IntegerField(
        default=0,
        help_text=(
            "Count of sessions that stayed on the destination page for 60s+ "
            "(suggestion_destination_dwell_60s event). Strong positive signal."
        ),
    )
    avg_engagement_time_seconds = models.FloatField(default=0.0)
    total_engagement_time_seconds = models.FloatField(default=0.0)
    event_count = models.IntegerField(default=0)
    is_attributed = models.BooleanField(default=True)
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Suggestion Telemetry Daily"
        verbose_name_plural = "Suggestion Telemetry Daily"
        ordering = ["-date", "telemetry_source", "-clicks"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "date",
                    "telemetry_source",
                    "suggestion",
                    "algorithm_version_slug",
                    "device_category",
                    "default_channel_group",
                    "source_medium",
                    "country",
                    "region",
                    "is_attributed",
                ],
                name="analytics_telemetry_daily_unique_rollup",
            )
        ]
        indexes = [
            models.Index(fields=["algorithm_version_slug", "date"]),
            models.Index(fields=["telemetry_source", "date"]),
            models.Index(fields=["suggestion", "-date"]),
            models.Index(fields=["destination", "-date"]),
            models.Index(fields=["device_category", "date"]),
            models.Index(fields=["default_channel_group", "date"]),
        ]

    def __str__(self) -> str:
        target = self.suggestion_id or "unattributed"
        return f"[{self.telemetry_source}] {target} on {self.date}"


class TelemetryCoverageDaily(models.Model):
    """Daily health rollup that shows whether telemetry is trustworthy."""

    COVERAGE_STATE_CHOICES = [
        ("healthy", "Healthy"),
        ("partial", "Partial"),
        ("degraded", "Degraded"),
    ]

    date = models.DateField(db_index=True)
    event_schema = models.CharField(max_length=50, default="fr016_v1")
    source_label = models.CharField(max_length=50, blank=True)
    algorithm_version_slug = models.CharField(max_length=100, blank=True)
    expected_instrumented_links = models.IntegerField(default=0)
    observed_impression_links = models.IntegerField(default=0)
    observed_click_links = models.IntegerField(default=0)
    attributed_destination_sessions = models.IntegerField(default=0)
    unattributed_destination_sessions = models.IntegerField(default=0)
    duplicate_event_drops = models.IntegerField(default=0)
    missing_metadata_events = models.IntegerField(default=0)
    delayed_rows_rewritten = models.IntegerField(default=0)
    coverage_state = models.CharField(
        max_length=20, choices=COVERAGE_STATE_CHOICES, default="partial"
    )
    last_synced_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Telemetry Coverage Daily"
        verbose_name_plural = "Telemetry Coverage Daily"
        ordering = ["-date", "source_label", "algorithm_version_slug"]
        constraints = [
            models.UniqueConstraint(
                fields=[
                    "date",
                    "event_schema",
                    "source_label",
                    "algorithm_version_slug",
                ],
                name="analytics_coverage_daily_unique_rollup",
            )
        ]

    def __str__(self) -> str:
        return f"{self.date} {self.coverage_state}"


class AnalyticsSyncRun(models.Model):
    """Audit row for one analytics import or restatement run."""

    SOURCE_CHOICES = [
        ("ga4", "Google Analytics 4"),
        ("matomo", "Matomo"),
        ("gsc", "Google Search Console"),
    ]
    STATUS_CHOICES = [
        ("pending", "Pending"),
        ("running", "Running"),
        ("completed", "Completed"),
        ("failed", "Failed"),
    ]

    source = models.CharField(max_length=20, choices=SOURCE_CHOICES, db_index=True)
    started_at = models.DateTimeField(auto_now_add=True, db_index=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default="pending", db_index=True
    )
    lookback_days = models.IntegerField(default=7)
    rows_read = models.IntegerField(default=0)
    rows_written = models.IntegerField(default=0)
    rows_updated = models.IntegerField(default=0)
    error_message = models.TextField(blank=True)

    class Meta:
        verbose_name = "Analytics Sync Run"
        verbose_name_plural = "Analytics Sync Runs"
        ordering = ["-started_at"]
        indexes = [
            models.Index(fields=["source", "-started_at"]),
            models.Index(fields=["status", "-started_at"]),
        ]

    def __str__(self) -> str:
        return f"{self.source} {self.status} at {self.started_at}"


class GSCDailyPerformance(models.Model):
    """
    Stores raw daily performance rows for a specific page from Google Search Console.
    This acts as the source for the attribution engine.
    """

    page_url = models.URLField(max_length=2000, db_index=True)
    date = models.DateField(db_index=True)
    impressions = models.PositiveIntegerField(default=0)
    clicks = models.PositiveIntegerField(default=0)
    avg_position = models.FloatField(default=0.0)
    ctr = models.FloatField(default=0.0)
    property_url = models.CharField(
        max_length=500, blank=True, help_text="The GSC property this belongs to."
    )

    class Meta:
        verbose_name = "GSC Daily Performance"
        verbose_name_plural = "GSC Daily Performance Rows"
        unique_together = [["page_url", "date", "property_url"]]
        indexes = [
            models.Index(fields=["date", "page_url"]),
        ]

    def __str__(self) -> str:
        return f"{self.page_url} on {self.date}"


class GSCImpactSnapshot(models.Model):
    """
    Stores the formalized FR-017 attribution impact for an applied suggestion.
    """

    WINDOW_TYPE_CHOICES = [
        ("7d", "7 Days"),
        ("14d", "14 Days"),
        ("28d", "28 Days"),
        ("90d", "90 Days"),
    ]

    REWARD_LABEL_CHOICES = [
        ("positive", "Positive"),
        ("neutral", "Neutral"),
        ("negative", "Negative"),
        ("inconclusive", "Inconclusive"),
    ]

    suggestion = models.ForeignKey(
        "suggestions.Suggestion",
        on_delete=models.CASCADE,
        related_name="gsc_impacts",
        help_text="The suggestion this attribution belongs to.",
    )
    apply_date = models.DateTimeField(db_index=True)
    window_type = models.CharField(
        max_length=10, choices=WINDOW_TYPE_CHOICES, default="28d"
    )

    baseline_clicks = models.IntegerField(default=0)
    post_clicks = models.IntegerField(default=0)
    baseline_impressions = models.IntegerField(default=0)
    post_impressions = models.IntegerField(default=0)
    lift_clicks_pct = models.FloatField(
        default=0.0, help_text="Relative click lift: (post - baseline) / baseline."
    )
    lift_clicks_absolute = models.IntegerField(default=0)

    probability_of_uplift = models.FloatField(
        default=0.0, help_text="Bayesian probability of positive lift (0.0 to 1.0)."
    )
    reward_label = models.CharField(
        max_length=20, choices=REWARD_LABEL_CHOICES, default="inconclusive"
    )

    last_computed_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "GSC Impact Snapshot"
        verbose_name_plural = "GSC Impact Snapshots"
        unique_together = [["suggestion", "window_type"]]
        ordering = ["-apply_date"]

    def __str__(self) -> str:
        return f"GSC Impact: {self.suggestion_id} ({self.reward_label})"


class WatchedPage(models.Model):
    """A user-bookmarked page to track SEO metrics over time (Stage 7)."""

    content_item = models.ForeignKey(
        "content.ContentItem",
        on_delete=models.CASCADE,
        related_name="watchers",
    )
    added_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(
        blank=True, help_text="User notes about why they're watching this page."
    )

    class Meta:
        verbose_name = "Watched Page"
        verbose_name_plural = "Watched Pages"
        ordering = ["-added_at"]
        unique_together = [["content_item"]]

    def __str__(self) -> str:
        return f"Watching: {self.content_item_id}"
