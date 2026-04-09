"""FR-025 — DRF serializers for co-occurrence and behavioral hub models."""

from __future__ import annotations

from rest_framework import serializers

from .models import (
    BehavioralHub,
    BehavioralHubMembership,
    SessionCoOccurrencePair,
    SessionCoOccurrenceRun,
)


class SessionCoOccurrencePairSerializer(serializers.ModelSerializer):
    source_content_item_id = serializers.IntegerField(source="source_content_item_id")
    dest_content_item_id = serializers.IntegerField(source="dest_content_item_id")
    source_title = serializers.SerializerMethodField()
    dest_title = serializers.SerializerMethodField()

    class Meta:
        model = SessionCoOccurrencePair
        fields = [
            "id",
            "source_content_item_id",
            "dest_content_item_id",
            "source_title",
            "dest_title",
            "co_session_count",
            "source_session_count",
            "dest_session_count",
            "jaccard_similarity",
            "lift",
            "data_window_start",
            "data_window_end",
            "last_computed_at",
        ]
        read_only_fields = fields

    def get_source_title(self, obj: SessionCoOccurrencePair) -> str:
        if hasattr(obj, "source_content_item") and obj.source_content_item:
            return obj.source_content_item.title or ""
        return ""

    def get_dest_title(self, obj: SessionCoOccurrencePair) -> str:
        if hasattr(obj, "dest_content_item") and obj.dest_content_item:
            return obj.dest_content_item.title or ""
        return ""


class SessionCoOccurrenceRunSerializer(serializers.ModelSerializer):
    class Meta:
        model = SessionCoOccurrenceRun
        fields = [
            "run_id",
            "status",
            "data_window_start",
            "data_window_end",
            "sessions_processed",
            "pairs_written",
            "ga4_rows_fetched",
            "started_at",
            "completed_at",
            "error_message",
        ]
        read_only_fields = fields


class BehavioralHubMembershipSerializer(serializers.ModelSerializer):
    content_item_id = serializers.IntegerField(source="content_item_id")
    content_item_title = serializers.SerializerMethodField()
    content_item_url = serializers.SerializerMethodField()

    class Meta:
        model = BehavioralHubMembership
        fields = [
            "id",
            "content_item_id",
            "content_item_title",
            "content_item_url",
            "membership_source",
            "co_occurrence_strength",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "content_item_title",
            "content_item_url",
            "created_at",
        ]

    def get_content_item_title(self, obj: BehavioralHubMembership) -> str:
        if hasattr(obj, "content_item") and obj.content_item:
            return obj.content_item.title or ""
        return ""

    def get_content_item_url(self, obj: BehavioralHubMembership) -> str:
        if hasattr(obj, "content_item") and obj.content_item:
            return obj.content_item.url or ""
        return ""


class BehavioralHubSerializer(serializers.ModelSerializer):
    class Meta:
        model = BehavioralHub
        fields = [
            "hub_id",
            "name",
            "detection_method",
            "min_jaccard_used",
            "member_count",
            "auto_link_enabled",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "hub_id",
            "detection_method",
            "min_jaccard_used",
            "member_count",
            "created_at",
            "updated_at",
        ]


class BehavioralHubDetailSerializer(BehavioralHubSerializer):
    members = BehavioralHubMembershipSerializer(
        source="memberships", many=True, read_only=True
    )

    class Meta(BehavioralHubSerializer.Meta):
        fields = BehavioralHubSerializer.Meta.fields + ["members"]
        read_only_fields = BehavioralHubSerializer.Meta.read_only_fields + ["members"]
