from rest_framework import serializers
from .models import GSCImpactSnapshot, GSCKeywordImpact

class GSCImpactSnapshotSerializer(serializers.ModelSerializer):
    """Serializer for suggestion-level search attribution."""
    
    anchor_phrase = serializers.CharField(source="suggestion.anchor_phrase", read_only=True)
    destination_title = serializers.CharField(source="suggestion.destination_title", read_only=True)
    status = serializers.CharField(source="suggestion.status", read_only=True)
    
    class Meta:
        model = GSCImpactSnapshot
        fields = [
            "suggestion_id",
            "anchor_phrase",
            "destination_title",
            "status",
            "apply_date",
            "window_type",
            "baseline_clicks",
            "post_clicks",
            "lift_clicks_pct",
            "lift_clicks_absolute",
            "probability_of_uplift",
            "reward_label",
            "last_computed_at",
        ]

class GSCKeywordImpactSerializer(serializers.ModelSerializer):
    """Serializer for query-level search attribution."""
    
    class Meta:
        model = GSCKeywordImpact
        fields = [
            "query",
            "clicks_baseline",
            "clicks_post",
            "impressions_baseline",
            "impressions_post",
            "lift_percent",
            "is_anchor_match",
        ]
