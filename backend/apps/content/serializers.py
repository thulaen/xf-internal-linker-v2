"""
Content app DRF serializers.

Serializers convert ContentItem, ScopeItem, Post, and Sentence models
to/from JSON for the Angular frontend API.
"""

from rest_framework import serializers

from .models import ContentItem, ContentMetricSnapshot, Post, ScopeItem, Sentence


class ScopeItemSerializer(serializers.ModelSerializer):
    """Serializes forum nodes and resource categories."""

    class Meta:
        model = ScopeItem
        fields = [
            "id", "scope_id", "scope_type", "title", "parent",
            "is_enabled", "content_count", "display_order",
        ]
        read_only_fields = ["id", "content_count"]


class ContentItemListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views — omits heavy fields like distilled_text."""

    scope_title = serializers.CharField(source="scope.title", read_only=True, default="")

    class Meta:
        model = ContentItem
        fields = [
            "id", "content_id", "content_type", "title", "url",
            "scope", "scope_title",
            "pagerank_score", "velocity_score",
            "view_count", "reply_count",
            "post_date", "is_deleted",
            "created_at", "updated_at",
        ]
        read_only_fields = fields


class ContentItemDetailSerializer(serializers.ModelSerializer):
    """Full serializer for detail views — includes distilled_text and embedding status."""

    scope_title = serializers.CharField(source="scope.title", read_only=True, default="")
    has_embedding = serializers.SerializerMethodField()
    has_post = serializers.SerializerMethodField()
    sentence_count = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = [
            "id", "content_id", "content_type", "title", "url",
            "scope", "scope_title",
            "distilled_text", "distill_method", "content_hash",
            "pagerank_score", "velocity_score",
            "view_count", "reply_count", "download_count",
            "post_date", "last_post_date",
            "xf_post_id", "xf_update_id",
            "is_deleted", "fetched_at",
            "has_embedding", "has_post", "sentence_count",
            "created_at", "updated_at",
        ]
        read_only_fields = fields

    def get_has_embedding(self, obj: ContentItem) -> bool:
        return obj.embedding is not None

    def get_has_post(self, obj: ContentItem) -> bool:
        return hasattr(obj, "post")

    def get_sentence_count(self, obj: ContentItem) -> int:
        return obj.sentences.count()


class PostSerializer(serializers.ModelSerializer):
    """Serializes post body data."""

    class Meta:
        model = Post
        fields = [
            "id", "content_item", "clean_text", "char_count", "word_count",
            "xf_post_id", "last_edit_date", "created_at", "updated_at",
        ]
        read_only_fields = fields


class SentenceSerializer(serializers.ModelSerializer):
    """Serializes individual extracted sentences."""

    class Meta:
        model = Sentence
        fields = [
            "id", "content_item", "position", "word_position",
            "text", "char_count", "start_char", "end_char",
        ]
        read_only_fields = fields
