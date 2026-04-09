from django.contrib import admin

from .models import CrawlSession, CrawledLink, CrawledPageMeta, SitemapConfig, SystemEvent


@admin.register(CrawlSession)
class CrawlSessionAdmin(admin.ModelAdmin):
    list_display = ["session_id", "site_domain", "status", "pages_crawled", "created_at"]
    list_filter = ["status", "site_domain"]
    readonly_fields = ["session_id", "created_at", "updated_at"]


@admin.register(CrawledPageMeta)
class CrawledPageMetaAdmin(admin.ModelAdmin):
    list_display = ["url", "http_status", "word_count", "title", "created_at"]
    list_filter = ["http_status", "session"]
    search_fields = ["url", "title"]


@admin.register(CrawledLink)
class CrawledLinkAdmin(admin.ModelAdmin):
    list_display = ["anchor_text", "destination_url", "context_class"]
    list_filter = ["context_class", "is_nofollow"]


@admin.register(SitemapConfig)
class SitemapConfigAdmin(admin.ModelAdmin):
    list_display = ["domain", "sitemap_url", "is_enabled", "last_fetch_at"]
    list_filter = ["is_enabled", "discovery_method"]


@admin.register(SystemEvent)
class SystemEventAdmin(admin.ModelAdmin):
    list_display = ["title", "severity", "source", "timestamp"]
    list_filter = ["severity", "source"]
    readonly_fields = ["event_id", "timestamp"]
