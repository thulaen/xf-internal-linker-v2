"""
Audit views — audit trail, reviewer scorecards, and silo leakage.
"""

from __future__ import annotations

from collections import defaultdict

from django.db.models import Count
from django.db.models.functions import TruncDate
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, UserRateThrottle
from rest_framework.views import APIView

from apps.api.query_params import coerce_int

from .models import (
    AuditEvent,
    ClientErrorLog,
    FeatureRequest,
    FeatureRequestVote,
    ReviewerScorecard,
    WebVital,
)
from .serializers import (
    AuditEventSerializer,
    ClientErrorLogSerializer,
    FeatureRequestSerializer,
    ReviewerScorecardSerializer,
    WebVitalSerializer,
)


class AuditEntryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/audit-entries/          — paginated audit trail
    GET /api/audit-entries/{id}/     — full entry with detail JSON
    GET /api/audit-entries/summary/  — action counts grouped by day
    """

    queryset = AuditEvent.objects.all()
    serializer_class = AuditEventSerializer
    permission_classes = [IsAuthenticated]
    filterset_fields = ["action", "subject_type"]

    def get_queryset(self):
        qs = AuditEvent.objects.all()
        target_type = self.request.query_params.get("target_type")
        target_id = self.request.query_params.get("target_id")
        if target_type:
            qs = qs.filter(subject_type=target_type)
        if target_id:
            qs = qs.filter(subject_id=target_id)
        return qs

    @action(detail=False, methods=["get"])
    def summary(self, request):
        """Action counts grouped by day (last 30 days by default)."""
        rows = (
            AuditEvent.objects.annotate(date=TruncDate("created_at"))
            .values("date", "action")
            .annotate(count=Count("id"))
            .order_by("-date")[:210]  # 30 days * 7 action types max
        )
        return Response(list(rows))


class ReviewerScorecardViewSet(viewsets.ReadOnlyModelViewSet):
    """
    GET /api/reviewer-scorecards/       — paginated scorecard list
    GET /api/reviewer-scorecards/{id}/  — single scorecard
    """

    queryset = ReviewerScorecard.objects.all()
    serializer_class = ReviewerScorecardSerializer
    permission_classes = [IsAuthenticated]


class SiloLeakageView(APIView):
    """
    GET /api/graph/silo-leakage/ — cross-silo link statistics.

    Returns total suggestions, cross-silo count, percentage, and per-pair breakdown.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.suggestions.models import Suggestion

        qs = Suggestion.objects.filter(
            status__in=("approved", "applied", "verified"),
            host__scope__silo_group__isnull=False,
            destination__scope__silo_group__isnull=False,
        ).select_related(
            "host__scope__silo_group",
            "destination__scope__silo_group",
        )

        total = qs.count()
        cross_silo: list[dict] = []
        pair_counts: dict[tuple[str, str], int] = defaultdict(int)
        cross_count = 0

        for s in qs.only(
            "host__scope__silo_group__name",
            "destination__scope__silo_group__name",
        ).iterator():
            src = getattr(
                getattr(getattr(s.host, "scope", None), "silo_group", None),
                "name",
                None,
            )
            dst = getattr(
                getattr(getattr(s.destination, "scope", None), "silo_group", None),
                "name",
                None,
            )
            if src and dst and src != dst:
                cross_count += 1
                pair_counts[(src, dst)] += 1

        for (src, dst), count in sorted(pair_counts.items(), key=lambda x: -x[1]):
            cross_silo.append({"source_silo": src, "target_silo": dst, "count": count})

        return Response(
            {
                "total_suggestions": total,
                "cross_silo_count": cross_count,
                "cross_silo_pct": round(cross_count / total * 100, 2)
                if total > 0
                else 0.0,
                "by_silo_pair": cross_silo[:50],
            }
        )


class ClientErrorLogView(APIView):
    """
    Phase U1 / Gap 26 — ingest endpoint for unhandled frontend
    exceptions captured by the Angular `GlobalErrorHandler`.

    `POST /api/telemetry/client-errors/`

    Auth-optional: the endpoint must accept errors from unauthenticated
    pages too (login page JS bug, token-expired states), but we still
    record the user id when available.

    Rate-limited per PYTHON-RULES §9.7 — a runaway render loop in the
    frontend could otherwise spam the backend. Both anon and user
    throttles use DRF's built-in classes (configured project-wide).
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        serializer = ClientErrorLogSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        # If a user is authenticated and didn't include their own id,
        # stamp it from the session so all their client errors are
        # attributable without the frontend having to know its user id.
        data = dict(serializer.validated_data)
        if not data.get("user_id") and getattr(request.user, "is_authenticated", False):
            data["user_id"] = request.user.pk

        ClientErrorLog.objects.create(**data)
        return Response({"status": "recorded"}, status=status.HTTP_201_CREATED)


class WebVitalView(APIView):
    """
    Phase E2 / Gap 51 — ingest endpoint for Core Web Vitals beacons.

    `POST /api/telemetry/web-vitals/`

    Fires from `frontend/src/app/core/services/web-vitals.service.ts`
    via `navigator.sendBeacon` (preferred) or `HttpClient` fallback.
    One row per metric fire per page-load.

    Auth-optional (same rationale as ClientErrorLogView — we want
    vitals on the login page too) but rate-limited to prevent abuse.
    """

    permission_classes = [AllowAny]
    throttle_classes = [AnonRateThrottle, UserRateThrottle]

    def post(self, request):
        serializer = WebVitalSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        data = dict(serializer.validated_data)

        # Map serializer field names to model field names. The frontend
        # payload uses short keys (`id`, `timestamp`); the model uses
        # disambiguated names (`metric_id`, `client_timestamp_ms`) so
        # they don't collide with Django's own `id` and `timestamp`
        # conventions.
        user_id = data.pop("user_id", None) if "user_id" in data else None
        if not user_id and getattr(request.user, "is_authenticated", False):
            user_id = request.user.pk

        WebVital.objects.create(
            name=data["name"],
            value=data["value"],
            rating=data.get("rating", "good"),
            delta=data.get("delta", 0.0),
            metric_id=data.get("id", ""),
            navigation_type=data.get("navigation_type", ""),
            path=data.get("path", ""),
            device_memory=data.get("device_memory"),
            effective_connection_type=data.get("effective_connection_type", ""),
            client_timestamp_ms=data.get("timestamp"),
            user_id=user_id,
        )
        return Response({"status": "recorded"}, status=status.HTTP_201_CREATED)


class _FeatureRequestThrottle(UserRateThrottle):
    """Cap feature-request submissions so a frustrated user can't spam the queue."""

    scope = "feature_request_submit"
    rate = "10/hour"


class FeatureRequestViewSet(viewsets.ModelViewSet):
    """Phase GB / Gap 151 — Feature request inbox.

    Endpoints::

      GET  /api/feature-requests/                  list (any authenticated user)
      POST /api/feature-requests/                  submit a new request
      GET  /api/feature-requests/{id}/             detail
      POST /api/feature-requests/{id}/vote/        upvote (idempotent per user)
      POST /api/feature-requests/{id}/set-status/  maintainer-only triage
      POST /api/feature-requests/{id}/reply/       maintainer reply

    Write actions (update / destroy) on the record itself are only
    permitted for staff. Regular users can only create and upvote.
    """

    queryset = FeatureRequest.objects.all().select_related("author")
    serializer_class = FeatureRequestSerializer
    permission_classes = [IsAuthenticated]
    http_method_names = ["get", "post", "head", "options"]

    def get_throttles(self):  # type: ignore[override]
        if self.action == "create":
            return [_FeatureRequestThrottle()]
        return super().get_throttles()

    def get_queryset(self):  # type: ignore[override]
        qs = super().get_queryset()
        # Allow filter by status / priority / category via query params —
        # keeps the triage admin UI simple without adding django-filter.
        params = self.request.query_params
        for field in ("status", "priority", "category"):
            v = params.get(field)
            if v:
                qs = qs.filter(**{field: v})
        return qs.order_by("-votes", "-created_at")

    def perform_create(self, serializer: FeatureRequestSerializer) -> None:  # type: ignore[override]
        user = self.request.user if self.request.user.is_authenticated else None
        # Capture a tiny environmental snapshot so maintainers can
        # reproduce without emailing back and forth. Client supplies
        # `context` keys; we add request-side user agent + IP for
        # forensics.
        submitted_context = serializer.validated_data.get("context") or {}
        if not isinstance(submitted_context, dict):
            submitted_context = {}
        submitted_context.setdefault(
            "user_agent", self.request.META.get("HTTP_USER_AGENT", "")[:400]
        )
        submitted_context.setdefault(
            "ip", self.request.META.get("REMOTE_ADDR", "")[:64]
        )
        serializer.save(author=user, context=submitted_context)

    @action(detail=True, methods=["post"], url_path="vote")
    def vote(self, request, pk=None):
        """Idempotent upvote — if the user has already voted, it's a no-op."""
        req = self.get_object()
        _, created = FeatureRequestVote.objects.get_or_create(
            request=req, user=request.user
        )
        if created:
            # Recompute from the source-of-truth table so concurrent
            # votes can't drift the denormalized counter.
            req.votes = req.vote_rows.count()
            req.save(update_fields=["votes", "updated_at"])
        return Response(
            {"votes": req.votes, "has_voted": True},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="unvote")
    def unvote(self, request, pk=None):
        req = self.get_object()
        deleted, _ = FeatureRequestVote.objects.filter(
            request=req, user=request.user
        ).delete()
        if deleted:
            req.votes = req.vote_rows.count()
            req.save(update_fields=["votes", "updated_at"])
        return Response(
            {"votes": req.votes, "has_voted": False},
            status=status.HTTP_200_OK,
        )

    @action(detail=True, methods=["post"], url_path="set-status")
    def set_status(self, request, pk=None):
        """Maintainer-only lifecycle transition."""
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        req = self.get_object()
        new_status = (request.data.get("status") or "").strip()
        valid = {c[0] for c in FeatureRequest.STATUS_CHOICES}
        if new_status not in valid:
            return Response(
                {"detail": f"status must be one of {sorted(valid)}"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        req.status = new_status
        req.save(update_fields=["status", "updated_at"])
        return Response(self.get_serializer(req).data, status=status.HTTP_200_OK)

    @action(detail=True, methods=["post"], url_path="reply")
    def reply(self, request, pk=None):
        """Maintainer adds a public reply the submitter will see."""
        if not request.user.is_staff:
            return Response({"detail": "Staff only."}, status=status.HTTP_403_FORBIDDEN)
        req = self.get_object()
        body = (request.data.get("admin_reply") or "").strip()[:10_000]
        req.admin_reply = body
        req.save(update_fields=["admin_reply", "updated_at"])
        return Response(self.get_serializer(req).data, status=status.HTTP_200_OK)


# ── Phase 4.1 — Undo History Timeline views ──────────────────────


class UndoTimelineView(APIView):
    """GET /api/audit/timeline/

    Returns the most recent restorable AuditEvent rows the operator
    can roll back. Supports filters: ``?subject_type=appsetting``,
    ``?actor=jane``, ``?lookback_days=7``, ``?limit=50``.

    Plain-English: shows yesterday-and-earlier setting changes with a
    Restore button next to each one. Backend returns enough info
    (old vs new value) to render a side-by-side diff.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.audit.services.undo_timeline import (
            DEFAULT_LOOKBACK_DAYS,
            list_restorable_events,
        )

        # Refactor 2026-05-04: shared apps.api.query_params.coerce_int
        # — same safe-fallback as the rest of the views.
        lookback_days = coerce_int(
            request.query_params.get("lookback_days"),
            default=DEFAULT_LOOKBACK_DAYS,
            min_value=1,
            max_value=365,
        )
        limit = coerce_int(
            request.query_params.get("limit"),
            default=100,
            min_value=1,
            max_value=1000,
        )
        subject_type_filter = request.query_params.get("subject_type") or None
        actor_filter = request.query_params.get("actor") or None

        entries = list_restorable_events(
            lookback_days=lookback_days,
            subject_type_filter=subject_type_filter,
            actor_filter=actor_filter,
            limit=limit,
        )
        return Response(
            {
                "lookback_days": lookback_days,
                "count": len(entries),
                "entries": [asdict(e) for e in entries],
            }
        )


class UndoRestoreView(APIView):
    """POST /api/audit/timeline/<event_id>/restore/

    Applies the inverse of one audit event. Records a NEW AuditEvent
    for the rollback (so timeline stays honest). Returns 200 with
    ``{ok, message, new_event_id}`` even on logical failure (UI shows
    the message); only 4xx/5xx for auth or shape errors.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, event_id: int):
        from apps.audit.services.undo_timeline import restore_event

        try:
            actor = getattr(request.user, "username", "") or str(
                getattr(request.user, "pk", "")
            )
        except Exception:  # noqa: forbidden-pattern silent-except — anonymous-user / weird auth payload; empty actor string is the right default.
            actor = ""

        result = restore_event(int(event_id), actor=actor, request=request)
        return Response(
            {
                "ok": result.ok,
                "message": result.message,
                "new_event_id": result.new_event_id,
            },
            status=status.HTTP_200_OK,
        )
