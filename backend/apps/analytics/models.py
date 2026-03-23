"""
Analytics models — GSC/GA4 search metrics and before/after impact reports.

SearchMetric stores daily performance data pulled from Google Search Console
and Google Analytics 4. ImpactReport compares metrics before vs. after a
suggestion was applied to measure real SEO impact.
"""

from django.db import models

from apps.core.models import TimestampedModel


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
    created_at = models.DateTimeField(
        auto_now_add=True,
        help_text="When this impact report was generated.",
    )

    class Meta:
        verbose_name = "Impact Report"
        verbose_name_plural = "Impact Reports"
        ordering = ["-created_at"]

    def __str__(self) -> str:
        sign = "+" if self.delta_percent >= 0 else ""
        return f"{self.metric_type} {sign}{self.delta_percent:.1f}% for {self.suggestion}"
