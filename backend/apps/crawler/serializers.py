"""
Crawler DRF serializers.
"""

from rest_framework import serializers

from .models import (
    CrawlSession,
    CrawledLink,
    CrawledPageMeta,
    SitemapConfig,
    SystemEvent,
)


# ---------------------------------------------------------------------------
# CrawlSession
# ---------------------------------------------------------------------------
class CrawlSessionSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrawlSession
        fields = [
            "session_id",
            "status",
            "site_domain",
            "config",
            "pages_crawled",
            "pages_changed",
            "pages_skipped_304",
            "new_pages_discovered",
            "broken_links_found",
            "bytes_downloaded",
            "elapsed_seconds",
            "progress",
            "message",
            "is_resumable",
            "error_message",
            "started_at",
            "paused_at",
            "completed_at",
            "created_at",
        ]
        read_only_fields = fields


class CrawlSessionCreateSerializer(serializers.Serializer):
    """Input for starting a new crawl or resuming a paused one."""

    site_domain = serializers.CharField(
        max_length=255,
        required=False,
        allow_blank=True,
        help_text="Domain to crawl (e.g. 'goldmidi.com').",
    )
    resume_session_id = serializers.UUIDField(
        required=False,
        help_text="If resuming, the session_id to continue from.",
    )
    rate_limit = serializers.IntegerField(
        required=False, default=4, min_value=1, max_value=10
    )
    max_depth = serializers.IntegerField(
        required=False, default=5, min_value=1, max_value=10
    )

    def validate(self, attrs):
        if attrs.get("resume_session_id"):
            return attrs
        if not str(attrs.get("site_domain") or "").strip():
            raise serializers.ValidationError(
                {"site_domain": "Enter a site domain or choose a session to resume."}
            )
        return attrs


# ---------------------------------------------------------------------------
# CrawledPageMeta
# ---------------------------------------------------------------------------
class CrawledPageMetaSerializer(serializers.ModelSerializer):
    class Meta:
        model = CrawledPageMeta
        fields = [
            "id",
            "url",
            "http_status",
            "response_time_ms",
            "title",
            "meta_description",
            "canonical_url",
            "robots_meta",
            "has_viewport",
            "h1_text",
            "h1_count",
            "og_title",
            "structured_data_types",
            "word_count",
            "content_to_html_ratio",
            "img_total",
            "img_missing_alt",
            "internal_link_count",
            "external_link_count",
            "crawl_depth",
            "consecutive_404_count",
            "created_at",
        ]
        read_only_fields = fields


class CrawledPageMetaSummarySerializer(serializers.ModelSerializer):
    """Compact version for list views."""

    class Meta:
        model = CrawledPageMeta
        fields = [
            "id",
            "url",
            "http_status",
            "response_time_ms",
            "title",
            "word_count",
            "internal_link_count",
            "crawl_depth",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# CrawledLink
# ---------------------------------------------------------------------------
class CrawledLinkSerializer(serializers.ModelSerializer):
    source_url = serializers.CharField(source="page.url", read_only=True)

    class Meta:
        model = CrawledLink
        fields = [
            "id",
            "source_url",
            "destination_url",
            "anchor_text",
            "context_class",
            "is_nofollow",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# SitemapConfig
# ---------------------------------------------------------------------------
class SitemapConfigSerializer(serializers.ModelSerializer):
    class Meta:
        model = SitemapConfig
        fields = [
            "id",
            "domain",
            "sitemap_url",
            "normalized_url",
            "discovery_method",
            "is_enabled",
            "last_fetch_at",
            "last_url_count",
            "last_error",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "normalized_url",
            "last_fetch_at",
            "last_url_count",
            "last_error",
            "created_at",
        ]


class SitemapConfigCreateSerializer(serializers.Serializer):
    """Input for adding a new sitemap."""

    domain = serializers.CharField(max_length=255)
    sitemap_url = serializers.URLField(max_length=2000)


class SitemapAutoDiscoverSerializer(serializers.Serializer):
    """Input for auto-discovering sitemaps on a domain."""

    domain = serializers.CharField(max_length=255)
    base_url = serializers.URLField(
        max_length=2000,
        help_text="Base URL to check (e.g. 'https://goldmidi.com/community/').",
    )


# ---------------------------------------------------------------------------
# SystemEvent
# ---------------------------------------------------------------------------
class SystemEventSerializer(serializers.ModelSerializer):
    class Meta:
        model = SystemEvent
        fields = [
            "event_id",
            "severity",
            "source",
            "title",
            "detail",
            "metadata",
            "timestamp",
        ]
        read_only_fields = fields


# ---------------------------------------------------------------------------
# SEO Audit aggregation (read-only response serializers)
# ---------------------------------------------------------------------------
class SEOAuditSummarySerializer(serializers.Serializer):
    """Aggregated SEO audit counts for the latest crawl session."""

    total_pages = serializers.IntegerField()
    missing_title = serializers.IntegerField()
    duplicate_titles = serializers.IntegerField()
    missing_meta_description = serializers.IntegerField()
    missing_h1 = serializers.IntegerField()
    multiple_h1 = serializers.IntegerField()
    missing_canonical = serializers.IntegerField()
    noindexed_pages = serializers.IntegerField()
    thin_content = serializers.IntegerField()
    slow_pages = serializers.IntegerField()
    non_mobile = serializers.IntegerField()
    missing_og = serializers.IntegerField()
    images_missing_alt = serializers.IntegerField()
    broken_links = serializers.IntegerField()
    orphan_pages = serializers.IntegerField()


# ---------------------------------------------------------------------------
# Page context header (lightweight per-page freshness data)
# ---------------------------------------------------------------------------
class CrawlerContextSerializer(serializers.Serializer):
    """Lightweight data for the page context header bar."""

    last_crawl_at = serializers.DateTimeField(allow_null=True)
    total_pages_crawled = serializers.IntegerField()
    storage_bytes = serializers.IntegerField()
    active_session = CrawlSessionSerializer(allow_null=True)
