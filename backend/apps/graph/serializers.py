"""Graph app serializers."""

from rest_framework import serializers

from .models import BrokenLink


class BrokenLinkSerializer(serializers.ModelSerializer):
    """Serialize broken-link scan records for the Link Health UI."""

    source_content_title = serializers.CharField(source="source_content.title", read_only=True)
    source_content_url = serializers.CharField(source="source_content.url", read_only=True)

    class Meta:
        model = BrokenLink
        fields = [
            "broken_link_id",
            "source_content",
            "source_content_title",
            "source_content_url",
            "url",
            "http_status",
            "redirect_url",
            "first_detected_at",
            "last_checked_at",
            "status",
            "notes",
            "created_at",
            "updated_at",
        ]
        read_only_fields = [
            "broken_link_id",
            "source_content",
            "source_content_title",
            "source_content_url",
            "url",
            "http_status",
            "redirect_url",
            "first_detected_at",
            "last_checked_at",
            "created_at",
            "updated_at",
        ]
