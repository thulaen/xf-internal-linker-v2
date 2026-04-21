"""
Content app DRF serializers.

Serializers convert ContentItem, ScopeItem, Post, and Sentence models
to/from JSON for the Angular frontend API.
"""

from django.utils.text import slugify
from rest_framework import serializers

from apps.pipeline.services.embeddings import get_current_embedding_signature

from .models import ContentItem, Post, ScopeItem, Sentence, SiloGroup
from apps.pipeline.services.link_freshness import classify_freshness_bucket


class SiloGroupSerializer(serializers.ModelSerializer):
    """Serialize silo-group CRUD payloads."""

    scope_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = SiloGroup
        fields = [
            "id",
            "name",
            "slug",
            "description",
            "display_order",
            "scope_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "scope_count", "created_at", "updated_at"]

    def validate(self, attrs):
        attrs = super().validate(attrs)
        name = attrs.get("name") or getattr(self.instance, "name", "")
        slug = attrs.get("slug") or slugify(name)
        if not slug:
            raise serializers.ValidationError({"slug": "Slug is required."})
        attrs["slug"] = slug
        return attrs


class ScopeItemSerializer(serializers.ModelSerializer):
    """Serializes forum nodes, resource categories, and WordPress scopes."""

    silo_group_name = serializers.CharField(
        source="silo_group.name", read_only=True, default=""
    )
    parent_title = serializers.CharField(
        source="parent.title", read_only=True, default=""
    )
    source_label = serializers.SerializerMethodField()
    scope_type_label = serializers.CharField(
        source="get_scope_type_display", read_only=True
    )

    class Meta:
        model = ScopeItem
        fields = [
            "id",
            "scope_id",
            "scope_type",
            "scope_type_label",
            "source_label",
            "title",
            "parent",
            "parent_title",
            "silo_group",
            "silo_group_name",
            "is_enabled",
            "content_count",
            "display_order",
        ]
        read_only_fields = ["id", "content_count"]

    def get_source_label(self, obj: ScopeItem) -> str:
        return _scope_source_label(obj.scope_type)


class ContentItemListSerializer(serializers.ModelSerializer):
    """Lightweight serializer for list views; omits heavy fields like distilled_text."""

    scope_title = serializers.CharField(
        source="scope.title", read_only=True, default=""
    )
    source_label = serializers.SerializerMethodField()
    content_type_label = serializers.CharField(
        source="get_content_type_display", read_only=True
    )
    freshness_bucket = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = [
            "id",
            "content_id",
            "content_type",
            "content_type_label",
            "source_label",
            "title",
            "url",
            "scope",
            "scope_title",
            "march_2026_pagerank_score",
            "velocity_score",
            "link_freshness_score",
            "content_value_score",
            "freshness_bucket",
            "view_count",
            "reply_count",
            "post_date",
            "is_deleted",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_source_label(self, obj: ContentItem) -> str:
        return _content_source_label(obj.content_type)

    def get_freshness_bucket(self, obj: ContentItem) -> str:
        return classify_freshness_bucket(float(obj.link_freshness_score or 0.5))


class ContentItemDetailSerializer(serializers.ModelSerializer):
    """Full serializer for detail views; includes distilled_text and embedding status."""

    scope_title = serializers.CharField(
        source="scope.title", read_only=True, default=""
    )
    has_embedding = serializers.SerializerMethodField()
    has_post = serializers.SerializerMethodField()
    sentence_count = serializers.SerializerMethodField()
    source_label = serializers.SerializerMethodField()
    content_type_label = serializers.CharField(
        source="get_content_type_display", read_only=True
    )
    freshness_bucket = serializers.SerializerMethodField()

    class Meta:
        model = ContentItem
        fields = [
            "id",
            "content_id",
            "content_type",
            "content_type_label",
            "source_label",
            "title",
            "url",
            "scope",
            "scope_title",
            "distilled_text",
            "distill_method",
            "content_hash",
            "march_2026_pagerank_score",
            "velocity_score",
            "link_freshness_score",
            "content_value_score",
            "freshness_bucket",
            "view_count",
            "reply_count",
            "download_count",
            "post_date",
            "last_post_date",
            "xf_post_id",
            "xf_update_id",
            "is_deleted",
            "fetched_at",
            "has_embedding",
            "has_post",
            "sentence_count",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_has_embedding(self, obj: ContentItem) -> bool:
        return (
            obj.embedding is not None
            and obj.embedding_model_version == get_current_embedding_signature()
        )

    def get_has_post(self, obj: ContentItem) -> bool:
        return hasattr(obj, "post")

    def get_sentence_count(self, obj: ContentItem) -> int:
        return obj.sentences.count()

    def get_source_label(self, obj: ContentItem) -> str:
        return _content_source_label(obj.content_type)

    def get_freshness_bucket(self, obj: ContentItem) -> str:
        return classify_freshness_bucket(float(obj.link_freshness_score or 0.5))


class PostSerializer(serializers.ModelSerializer):
    """Serializes post body data."""

    class Meta:
        model = Post
        fields = [
            "id",
            "content_item",
            "clean_text",
            "char_count",
            "word_count",
            "xf_post_id",
            "last_edit_date",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields


class SentenceSerializer(serializers.ModelSerializer):
    """Serializes individual extracted sentences."""

    class Meta:
        model = Sentence
        fields = [
            "id",
            "content_item",
            "position",
            "word_position",
            "text",
            "char_count",
            "start_char",
            "end_char",
        ]
        read_only_fields = fields


def _scope_source_label(scope_type: str) -> str:
    if scope_type.startswith("wp_"):
        return "WordPress"
    return "XenForo"


def _content_source_label(content_type: str) -> str:
    if content_type.startswith("wp_"):
        return "WordPress"
    return "XenForo"
