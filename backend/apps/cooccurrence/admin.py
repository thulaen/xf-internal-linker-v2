"""FR-025 — Django admin for co-occurrence models."""

from django.contrib import admin

from .models import (
    BehavioralHub,
    BehavioralHubMembership,
    SessionCoOccurrencePair,
    SessionCoOccurrenceRun,
)


@admin.register(SessionCoOccurrencePair)
class SessionCoOccurrencePairAdmin(admin.ModelAdmin):
    list_display = [
        "source_content_item",
        "dest_content_item",
        "co_session_count",
        "jaccard_similarity",
        "lift",
        "data_window_start",
        "data_window_end",
    ]
    list_filter = ["data_window_start"]
    search_fields = ["source_content_item__title", "dest_content_item__title"]
    ordering = ["-jaccard_similarity"]
    readonly_fields = ["last_computed_at", "created_at", "updated_at"]


@admin.register(SessionCoOccurrenceRun)
class SessionCoOccurrenceRunAdmin(admin.ModelAdmin):
    list_display = [
        "run_id",
        "status",
        "sessions_processed",
        "pairs_written",
        "ga4_rows_fetched",
        "started_at",
        "completed_at",
    ]
    list_filter = ["status"]
    readonly_fields = [
        "run_id",
        "started_at",
        "completed_at",
        "sessions_processed",
        "pairs_written",
        "ga4_rows_fetched",
    ]
    ordering = ["-started_at"]


class BehavioralHubMembershipInline(admin.TabularInline):
    model = BehavioralHubMembership
    extra = 0
    fields = ["content_item", "membership_source", "co_occurrence_strength"]
    readonly_fields = ["created_at"]


@admin.register(BehavioralHub)
class BehavioralHubAdmin(admin.ModelAdmin):
    list_display = [
        "name",
        "member_count",
        "auto_link_enabled",
        "detection_method",
        "min_jaccard_used",
        "created_at",
    ]
    list_filter = ["auto_link_enabled", "detection_method"]
    search_fields = ["name"]
    readonly_fields = ["hub_id", "member_count", "created_at", "updated_at"]
    inlines = [BehavioralHubMembershipInline]


@admin.register(BehavioralHubMembership)
class BehavioralHubMembershipAdmin(admin.ModelAdmin):
    list_display = [
        "hub",
        "content_item",
        "membership_source",
        "co_occurrence_strength",
        "created_at",
    ]
    list_filter = ["membership_source"]
    search_fields = ["hub__name", "content_item__title"]
    readonly_fields = ["created_at"]
