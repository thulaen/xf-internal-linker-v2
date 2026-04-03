"""
Analytics admin — SearchMetric and ImpactReport.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import (
    AnalyticsSyncRun, GSCDailyPerformance, GSCImpactSnapshot, 
    ImpactReport, SearchMetric, SuggestionTelemetryDaily, TelemetryCoverageDaily
)


@admin.register(SearchMetric)
class SearchMetricAdmin(ModelAdmin):
    """Admin for daily GSC/GA4 performance data."""

    list_display = [
        "content_item", "date", "source", "impressions", "clicks", "ctr",
        "average_position", "page_views",
    ]
    list_filter = ["source", "date"]
    search_fields = ["content_item__title", "query"]
    readonly_fields = [
        "content_item", "date", "source", "impressions", "clicks",
        "ctr", "average_position", "query",
        "page_views", "sessions", "avg_engagement_time", "bounce_rate",
    ]
    ordering = ["-date"]
    date_hierarchy = "date"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(ImpactReport)
class ImpactReportAdmin(ModelAdmin):
    """Admin for before/after impact reports on applied suggestions."""

    list_display = ["suggestion", "metric_type", "before_value", "after_value",
                    "delta_display", "created_at"]
    list_filter = ["metric_type"]
    search_fields = ["suggestion__destination_title"]
    readonly_fields = [
        "suggestion", "metric_type", "before_value", "after_value",
        "before_date_range", "after_date_range", "delta_percent", "created_at",
    ]
    ordering = ["-created_at"]

    @admin.display(description="Change")
    def delta_display(self, obj: ImpactReport) -> str:
        sign = "+" if obj.delta_percent >= 0 else ""
        return f"{sign}{obj.delta_percent:.1f}%"

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(SuggestionTelemetryDaily)
class SuggestionTelemetryDailyAdmin(ModelAdmin):
    """Admin for daily suggestion telemetry rollups."""

    list_display = [
        "date", "telemetry_source", "suggestion", "clicks", "impressions",
        "destination_views", "engaged_sessions", "is_attributed",
    ]
    list_filter = ["telemetry_source", "date", "is_attributed", "device_category", "default_channel_group"]
    search_fields = ["suggestion__anchor_phrase", "algorithm_version_slug", "source_label"]
    readonly_fields = [field.name for field in SuggestionTelemetryDaily._meta.fields]
    ordering = ["-date", "telemetry_source", "-clicks"]
    date_hierarchy = "date"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(TelemetryCoverageDaily)
class TelemetryCoverageDailyAdmin(ModelAdmin):
    """Admin for telemetry health rollups."""

    list_display = [
        "date", "source_label", "algorithm_version_slug", "coverage_state",
        "expected_instrumented_links", "observed_click_links",
    ]
    list_filter = ["coverage_state", "date", "source_label"]
    search_fields = ["algorithm_version_slug", "source_label", "event_schema"]
    readonly_fields = [field.name for field in TelemetryCoverageDaily._meta.fields]
    ordering = ["-date"]
    date_hierarchy = "date"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(AnalyticsSyncRun)
class AnalyticsSyncRunAdmin(ModelAdmin):
    """Admin for telemetry sync runs."""

    list_display = [
        "source", "status", "started_at", "completed_at",
        "lookback_days", "rows_read", "rows_written", "rows_updated",
    ]
    list_filter = ["source", "status"]
    search_fields = ["error_message"]
    readonly_fields = [field.name for field in AnalyticsSyncRun._meta.fields]
    ordering = ["-started_at"]

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False


@admin.register(GSCDailyPerformance)
class GSCDailyPerformanceAdmin(ModelAdmin):
    """Admin for raw GSC performance data."""

    list_display = ["page_url", "date", "impressions", "clicks", "avg_position", "ctr"]
    list_filter = ["date", "property_url"]
    search_fields = ["page_url"]
    readonly_fields = [field.name for field in GSCDailyPerformance._meta.fields]
    ordering = ["-date", "page_url"]
    date_hierarchy = "date"

    def has_add_permission(self, request) -> bool:
        return False


@admin.register(GSCImpactSnapshot)
class GSCImpactSnapshotAdmin(ModelAdmin):
    """Admin for the formalized FR-017 GSC impact attribution."""

    list_display = [
        "suggestion", "apply_date", "window_type", "reward_label",
        "lift_clicks_pct", "probability_of_uplift",
    ]
    list_filter = ["reward_label", "window_type"]
    search_fields = ["suggestion__destination_title", "suggestion_id"]
    readonly_fields = [field.name for field in GSCImpactSnapshot._meta.fields]
    ordering = ["-apply_date"]
    date_hierarchy = "apply_date"

    def has_add_permission(self, request) -> bool:
        return False
