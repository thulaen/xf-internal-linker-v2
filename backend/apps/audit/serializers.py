"""Serializers for the audit trail and reviewer scorecards."""

from rest_framework import serializers

from .models import (
    AuditEntry,
    ErrorLog,
    FeatureRequest,
    ReviewerScorecard,
)


class AuditEntrySerializer(serializers.ModelSerializer):
    class Meta:
        model = AuditEntry
        fields = [
            "id",
            "action",
            "target_type",
            "target_id",
            "detail",
            "ip_address",
            "created_at",
        ]
        read_only_fields = fields


class ReviewerScorecardSerializer(serializers.ModelSerializer):
    class Meta:
        model = ReviewerScorecard
        fields = [
            "id",
            "period_start",
            "period_end",
            "total_reviewed",
            "approved_count",
            "rejected_count",
            "approval_rate",
            "verified_rate",
            "stale_rate",
            "avg_review_time_seconds",
            "top_rejection_reasons",
            "created_at",
        ]
        read_only_fields = fields


class ErrorLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = ErrorLog
        fields = [
            "id",
            "job_type",
            "step",
            "error_message",
            "raw_exception",
            "why",
            "acknowledged",
            "created_at",
        ]
        read_only_fields = [
            "id",
            "job_type",
            "step",
            "error_message",
            "raw_exception",
            "why",
            "created_at",
        ]


class ClientErrorLogSerializer(serializers.Serializer):
    """
    Phase U1 / Gap 26 — inbound serializer for the GlobalErrorHandler
    endpoint. Write-only view of ClientErrorLog; read is via admin.

    Uses a plain `Serializer` (not `ModelSerializer`) because we need
    pre-validation truncation rather than rejection — a buggy client
    that sends a 2000-char user_agent should still land in the log,
    just clipped. The view's `create(**validated_data)` still hits the
    model fields directly.
    """

    message = serializers.CharField(required=True, allow_blank=False)
    stack = serializers.CharField(required=False, allow_blank=True, default="")
    route = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
    url = serializers.URLField(required=False, allow_blank=True, default="", max_length=1000)
    user_agent = serializers.CharField(required=False, allow_blank=True, default="")
    app_version = serializers.CharField(required=False, allow_blank=True, default="", max_length=50)
    user_id = serializers.IntegerField(required=False, allow_null=True, default=None)
    context = serializers.JSONField(required=False, default=dict)

    def validate_message(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("message is required.")
        return value[:4000]

    def validate_stack(self, value: str) -> str:
        return (value or "")[:16000]

    def validate_user_agent(self, value: str) -> str:
        return (value or "")[:500]

    def validate_context(self, value: object) -> object:
        if value is None:
            return {}
        if not isinstance(value, dict):
            raise serializers.ValidationError("context must be a JSON object.")
        return value


class WebVitalSerializer(serializers.Serializer):
    """
    Phase E2 / Gap 51 — inbound serializer for the WebVitalsService beacon
    at `POST /api/telemetry/web-vitals/`.

    A plain Serializer (not ModelSerializer) so we can be permissive about
    unknown fields — browser extensions and future `web-vitals` versions
    may add fields we don't know about yet, and dropping the beacon would
    be worse than dropping the extra fields.

    Field names mirror the payload shape in
    `frontend/src/app/core/services/web-vitals.service.ts::report()`.
    """

    # Whitelist of metrics we accept. Anything else is silently dropped
    # by validate_name() — the frontend should never send these, but if
    # a browser extension injects a custom metric we don't want 400s.
    ALLOWED_METRICS = {"LCP", "CLS", "INP", "FCP", "TTFB"}
    ALLOWED_RATINGS = {"good", "needs-improvement", "poor"}

    name = serializers.CharField(required=True, max_length=10)
    value = serializers.FloatField(required=True)
    rating = serializers.CharField(required=False, allow_blank=True, default="good")
    delta = serializers.FloatField(required=False, default=0.0)
    id = serializers.CharField(required=False, allow_blank=True, default="", max_length=100)
    navigation_type = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
        max_length=20,
    )
    path = serializers.CharField(required=False, allow_blank=True, default="", max_length=500)
    device_memory = serializers.FloatField(required=False, allow_null=True, default=None)
    effective_connection_type = serializers.CharField(
        required=False,
        allow_blank=True,
        allow_null=True,
        default="",
        max_length=10,
    )
    timestamp = serializers.IntegerField(required=False, allow_null=True, default=None)

    def validate_name(self, value: str) -> str:
        value = (value or "").strip().upper()
        if value not in self.ALLOWED_METRICS:
            raise serializers.ValidationError(
                f"name must be one of {sorted(self.ALLOWED_METRICS)}",
            )
        return value

    def validate_rating(self, value: str) -> str:
        value = (value or "good").strip().lower()
        if value not in self.ALLOWED_RATINGS:
            # Bad rating is not fatal — default to 'good' so the beacon
            # still lands.
            return "good"
        return value

    def validate_value(self, value: float) -> float:
        # Sanity clamp — a Web Vital timing above an hour is obviously
        # bogus (web-vitals library caps much sooner). Dropping is worse
        # than clipping, so clip and keep.
        if value < 0:
            return 0.0
        if value > 3_600_000.0:  # 1 hour in ms
            return 3_600_000.0
        return value

    def validate_path(self, value: str) -> str:
        value = (value or "").strip()
        # Strip any accidentally-included query string — web-vitals.service
        # already sends pathname-only, but defence in depth.
        if "?" in value:
            value = value.split("?", 1)[0]
        return value[:500]

    def validate_navigation_type(self, value: str | None) -> str:
        return (value or "")[:20]

    def validate_effective_connection_type(self, value: str | None) -> str:
        return (value or "")[:10]


class FeatureRequestSerializer(serializers.ModelSerializer):
    """Phase GB / Gap 151 — serializer for the in-app feature-request inbox.

    Read path exposes aggregated vote count and the submitter's username.
    Write path restricts the fields an operator can set — ``status``,
    ``votes``, and ``admin_reply`` are maintainer-only and mutated via
    the viewset's dedicated actions.
    """

    author_username = serializers.SerializerMethodField()
    has_voted = serializers.SerializerMethodField()

    class Meta:
        model = FeatureRequest
        fields = [
            "id",
            "created_at",
            "updated_at",
            "author",
            "author_username",
            "title",
            "body",
            "category",
            "priority",
            "status",
            "context",
            "votes",
            "admin_reply",
            "has_voted",
        ]
        read_only_fields = [
            "id",
            "created_at",
            "updated_at",
            "author",
            "author_username",
            "status",
            "votes",
            "admin_reply",
            "has_voted",
        ]
        extra_kwargs = {
            "title": {"max_length": 160},
        }

    def get_author_username(self, obj: FeatureRequest) -> str:
        return getattr(obj.author, "username", "") or ""

    def get_has_voted(self, obj: FeatureRequest) -> bool:
        request = self.context.get("request")
        user = getattr(request, "user", None)
        if not user or not getattr(user, "is_authenticated", False):
            return False
        # Avoid an extra query per row when the viewset has already
        # annotated `user_has_voted` via a Subquery.
        pre = getattr(obj, "user_has_voted", None)
        if pre is not None:
            return bool(pre)
        return obj.vote_rows.filter(user=user).exists()

    def validate_title(self, value: str) -> str:
        value = (value or "").strip()
        if not value:
            raise serializers.ValidationError("Title is required.")
        return value[:160]

    def validate_body(self, value: str) -> str:
        value = (value or "").strip()
        if len(value) < 10:
            raise serializers.ValidationError(
                "Please describe the feature in at least 10 characters."
            )
        return value[:10_000]

    def validate_category(self, value: str | None) -> str:
        return (value or "").strip()[:40]
