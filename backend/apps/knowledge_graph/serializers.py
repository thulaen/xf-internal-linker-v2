"""Knowledge graph DRF serializers."""

from rest_framework import serializers

from .models import EntityNode


class EntityNodeSerializer(serializers.ModelSerializer):
    """Serializes EntityNode records with an annotated article_count field."""

    article_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = EntityNode
        fields = [
            "id",
            "entity_id",
            "surface_form",
            "canonical_form",
            "entity_type",
            "article_count",
            "created_at",
        ]
        read_only_fields = fields
