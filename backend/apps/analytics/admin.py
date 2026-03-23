"""
Analytics admin — SearchMetric and ImpactReport.
"""

from django.contrib import admin
from unfold.admin import ModelAdmin

from .models import ImpactReport, SearchMetric


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
