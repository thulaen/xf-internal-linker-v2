from rest_framework import serializers
from .models import GSCImpactSnapshot, GSCKeywordImpact

class GSCImpactSnapshotSerializer(serializers.ModelSerializer):
    """Serializer for suggestion-level search attribution."""

    anchor_phrase = serializers.CharField(source="suggestion.anchor_phrase", read_only=True)
    destination_title = serializers.CharField(source="suggestion.destination_title", read_only=True)
    status = serializers.CharField(source="suggestion.status", read_only=True)
    source_type = serializers.SerializerMethodField()
    source_label = serializers.SerializerMethodField()

    def get_source_type(self, obj) -> str:
        ct = getattr(getattr(obj.suggestion, "destination", None), "content_type", None)
        return "wordpress" if ct in ("wp_post", "wp_page") else "xenforo"

    def get_source_label(self, obj) -> str:
        ct = getattr(getattr(obj.suggestion, "destination", None), "content_type", None)
        return "WordPress" if ct in ("wp_post", "wp_page") else "XenForo"

    wilson_lower_bound = serializers.SerializerMethodField()
    wilson_confidence_label = serializers.SerializerMethodField()

    def get_wilson_lower_bound(self, obj) -> float:
        """
        Calculates the 95% Wilson Score Lower Bound for CTR.
        CTR_Wilson = (CTR + z^2/(2n) - z * sqrt((CTR * (1-CTR) + z^2/(4n)) / n)) / (1 + z^2/n)
        """
        n = obj.post_impressions
        if n < 1:
            return 0.0
            
        clicks = obj.post_clicks
        p = clicks / n
        z = 1.96  # 95% confidence
        
        denominator = 1 + (z**2 / n)
        adjustment = z**2 / (2 * n)
        error = z * ((p * (1 - p) + (z**2 / (4 * n))) / n)**0.5
        
        lower_bound = (p + adjustment - error) / denominator
        return round(max(0.0, lower_bound), 4)

    def get_wilson_confidence_label(self, obj) -> str:
        n = obj.post_impressions
        if n < 20:
            return "Low"
        if n < 100:
            return "Moderate"
        if n < 500:
            return "Good"
        return "High"

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
            "baseline_impressions",
            "post_impressions",
            "wilson_lower_bound",
            "wilson_confidence_label",
            "lift_clicks_pct",
            "lift_clicks_absolute",
            "probability_of_uplift",
            "reward_label",
            "last_computed_at",
            "source_type",
            "source_label",
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
