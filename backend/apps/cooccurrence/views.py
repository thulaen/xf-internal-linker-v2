"""FR-025 — REST API views for co-occurrence and behavioral hubs."""

from __future__ import annotations

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.query_params import (
    coerce_pagination,
    parse_float_strict,
    parse_int_strict,
)
from apps.api.throttles import (
    CoOccurrenceComputeThrottle as _CoOccurrenceComputeThrottle,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Default operational settings
# ---------------------------------------------------------------------------

DEFAULT_COOCCURRENCE_SETTINGS = {
    "cooccurrence_enabled": True,
    "data_window_days": 90,
    "min_co_session_count": 5,
    "min_jaccard": 0.05,
    "hub_min_jaccard": 0.15,
    "hub_min_members": 3,
    "hub_detection_enabled": True,
    "schedule_weekly": True,
}


def _read_cooccurrence_settings() -> dict:
    # Group D consolidation (2026-04-28): the inline ``_bool`` /
    # ``_int`` / ``_float`` closures used to live here; replaced with
    # the shared ``AppSetting.get_*`` classmethods so the cast
    # semantics stay consistent project-wide.
    from apps.core.models import AppSetting

    _bool = AppSetting.get_bool
    _int = AppSetting.get_int
    _float = AppSetting.get_float

    from .models import SessionCoOccurrenceRun, BehavioralHub

    last_run = (
        SessionCoOccurrenceRun.objects.filter(
            status=SessionCoOccurrenceRun.STATUS_COMPLETED
        )
        .order_by("-completed_at")
        .first()
    )

    return {
        "cooccurrence_enabled": _bool("cooccurrence.enabled", True),
        "data_window_days": _int("cooccurrence.data_window_days", 90),
        "min_co_session_count": _int("cooccurrence.min_co_session_count", 5),
        "min_jaccard": _float("cooccurrence.min_jaccard", 0.05),
        "hub_min_jaccard": _float("cooccurrence.hub_min_jaccard", 0.15),
        "hub_min_members": _int("cooccurrence.hub_min_members", 3),
        "hub_detection_enabled": _bool("cooccurrence.hub_detection_enabled", True),
        "schedule_weekly": _bool("cooccurrence.schedule_weekly", True),
        # read-only stats
        "last_run_at": last_run.completed_at.isoformat() if last_run else None,
        "last_run_pairs_written": last_run.pairs_written if last_run else 0,
        "last_run_hubs_detected": BehavioralHub.objects.count(),
    }


# ---------------------------------------------------------------------------
# Co-occurrence pair views
# ---------------------------------------------------------------------------


class CoOccurrencePairListView(APIView):
    """GET /api/cooccurrence/pairs/ — list pairs with optional filters."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import SessionCoOccurrencePair
        from .serializers import SessionCoOccurrencePairSerializer

        qs = SessionCoOccurrencePair.objects.select_related(
            "source_content_item", "dest_content_item"
        ).order_by("-jaccard_similarity")

        # Refactor 2026-05-04: filter-coercion + pagination via the
        # shared apps.api.query_params helpers. Strict parsing on the
        # filter inputs (operator must see typos), silent fallback on
        # the paginator (operator should not get a 500 over a bad
        # `?page=foo`).
        min_jaccard_raw = request.query_params.get("min_jaccard")
        if min_jaccard_raw:
            parsed, err = parse_float_strict(
                min_jaccard_raw,
                field_name="min_jaccard",
                min_value=0.0,
                max_value=1.0,
            )
            if err:
                return Response({"detail": err}, status=400)
            qs = qs.filter(jaccard_similarity__gte=parsed)
        min_co_raw = request.query_params.get("min_co_sessions")
        if min_co_raw:
            parsed_int, err = parse_int_strict(
                min_co_raw,
                field_name="min_co_sessions",
                min_value=1,
            )
            if err:
                return Response({"detail": err}, status=400)
            qs = qs.filter(co_session_count__gte=parsed_int)

        page, page_size, offset = coerce_pagination(
            request.query_params, default_page_size=50, max_page_size=200
        )
        total = qs.count()
        pairs = qs[offset : offset + page_size]

        return Response(
            {
                "count": total,
                "results": SessionCoOccurrencePairSerializer(pairs, many=True).data,
            }
        )


class CoOccurrencePairBySourceView(APIView):
    """GET /api/cooccurrence/pairs/<source_id>/ — all pairs for a source content item."""

    permission_classes = [IsAuthenticated]

    def get(self, request, source_id: int):
        from .models import SessionCoOccurrencePair
        from .serializers import SessionCoOccurrencePairSerializer

        qs = (
            SessionCoOccurrencePair.objects.filter(source_content_item_id=source_id)
            .select_related("source_content_item", "dest_content_item")
            .order_by("-jaccard_similarity")
        )
        return Response(SessionCoOccurrencePairSerializer(qs, many=True).data)


# ---------------------------------------------------------------------------
# Run views
# ---------------------------------------------------------------------------


class CoOccurrenceRunListView(APIView):
    """GET /api/cooccurrence/runs/ — list computation run records."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import SessionCoOccurrenceRun
        from .serializers import SessionCoOccurrenceRunSerializer

        runs = SessionCoOccurrenceRun.objects.all()[:50]
        return Response(SessionCoOccurrenceRunSerializer(runs, many=True).data)


class TriggerCoOccurrenceView(APIView):
    """POST /api/cooccurrence/compute/ — trigger on-demand run."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [_CoOccurrenceComputeThrottle]

    def post(self, request):
        from .tasks import compute_session_cooccurrence

        result = compute_session_cooccurrence.delay()
        return Response({"task_id": result.id, "status": "queued"}, status=202)


# ---------------------------------------------------------------------------
# Behavioral hub views
# ---------------------------------------------------------------------------


class BehavioralHubListView(APIView):
    """GET /api/behavioral-hubs/ — list all hubs."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .models import BehavioralHub
        from .serializers import BehavioralHubSerializer

        qs = BehavioralHub.objects.all()
        # Refactor 2026-05-04: pagination via shared
        # apps.api.query_params.coerce_pagination — same safe-fallback +
        # range-clamp behaviour as the cooccurrence pairs endpoint.
        page, page_size, offset = coerce_pagination(
            request.query_params, default_page_size=25, max_page_size=100
        )
        total = qs.count()
        hubs = qs[offset : offset + page_size]
        return Response(
            {
                "count": total,
                "results": BehavioralHubSerializer(hubs, many=True).data,
            }
        )


class BehavioralHubDetailView(APIView):
    """GET/PATCH /api/behavioral-hubs/<hub_id>/"""

    permission_classes = [IsAuthenticated]

    def _get_hub(self, hub_id):
        from .models import BehavioralHub

        try:
            return BehavioralHub.objects.prefetch_related(
                "memberships__content_item"
            ).get(hub_id=hub_id)
        except BehavioralHub.DoesNotExist:
            return None

    def get(self, request, hub_id):
        from .serializers import BehavioralHubDetailSerializer

        hub = self._get_hub(hub_id)
        if hub is None:
            return Response({"error": "Not found."}, status=404)
        return Response(BehavioralHubDetailSerializer(hub).data)

    def patch(self, request, hub_id):
        from .serializers import BehavioralHubSerializer

        hub = self._get_hub(hub_id)
        if hub is None:
            return Response({"error": "Not found."}, status=404)

        allowed = {"name", "auto_link_enabled"}
        update_fields = []
        for field in allowed:
            if field in request.data:
                setattr(hub, field, request.data[field])
                update_fields.append(field)

        if update_fields:
            update_fields.append("updated_at")
            hub.save(update_fields=update_fields)

        return Response(BehavioralHubSerializer(hub).data)


class BehavioralHubMemberView(APIView):
    """POST /api/behavioral-hubs/<hub_id>/members/ — manually add a member."""

    permission_classes = [IsAuthenticated]

    def post(self, request, hub_id):
        from .models import BehavioralHub, BehavioralHubMembership

        try:
            hub = BehavioralHub.objects.get(hub_id=hub_id)
        except BehavioralHub.DoesNotExist:
            return Response({"error": "Not found."}, status=404)

        content_item_id = request.data.get("content_item_id")
        if not content_item_id:
            return Response({"error": "content_item_id required."}, status=400)

        membership, created = BehavioralHubMembership.objects.update_or_create(
            hub=hub,
            content_item_id=content_item_id,
            defaults={
                "membership_source": BehavioralHubMembership.SOURCE_MANUAL_ADD,
                "co_occurrence_strength": 0.0,
            },
        )
        hub.member_count = hub.memberships.exclude(
            membership_source=BehavioralHubMembership.SOURCE_MANUAL_REMOVE
        ).count()
        hub.save(update_fields=["member_count", "updated_at"])
        return Response(
            {"created": created, "membership_id": membership.pk},
            status=201 if created else 200,
        )


class BehavioralHubMemberDetailView(APIView):
    """DELETE /api/behavioral-hubs/<hub_id>/members/<content_item_id>/ — remove a member."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, hub_id, content_item_id: int):
        from .models import BehavioralHub, BehavioralHubMembership

        try:
            hub = BehavioralHub.objects.get(hub_id=hub_id)
        except BehavioralHub.DoesNotExist:
            return Response({"error": "Not found."}, status=404)

        # Mark as manual remove override rather than hard-deleting
        BehavioralHubMembership.objects.update_or_create(
            hub=hub,
            content_item_id=content_item_id,
            defaults={
                "membership_source": BehavioralHubMembership.SOURCE_MANUAL_REMOVE,
            },
        )
        hub.member_count = hub.memberships.exclude(
            membership_source=BehavioralHubMembership.SOURCE_MANUAL_REMOVE
        ).count()
        hub.save(update_fields=["member_count", "updated_at"])
        return Response(status=204)


class TriggerHubDetectionView(APIView):
    """POST /api/behavioral-hubs/detect/ — trigger hub detection on-demand."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from .tasks import detect_behavioral_hubs

        result = detect_behavioral_hubs.delay()
        return Response({"task_id": result.id, "status": "queued"}, status=202)


# ---------------------------------------------------------------------------
# Co-occurrence settings
# ---------------------------------------------------------------------------


class CoOccurrenceSettingsView(APIView):
    """
    GET  /api/settings/cooccurrence/ — return operational co-occurrence settings
    PUT  /api/settings/cooccurrence/ — persist settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(_read_cooccurrence_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        data = request.data

        def _persist_bool(key: str, field: str, default: bool) -> None:
            val = data.get(field)
            if val is None:
                return
            AppSetting.objects.update_or_create(
                key=key,
                defaults={"value": "true" if val else "false", "value_type": "bool"},
            )

        # Bug fix 2026-05-04: previously bad numeric input on settings
        # PUT silently did NOT persist, but returned 200 OK so the
        # operator thought the setting saved when it didn't. Collect
        # validation errors and surface them as a 400 below.
        validation_errors: dict[str, str] = {}

        def _persist_int(key: str, field: str, lo: int, hi: int) -> None:
            val = data.get(field)
            if val is None:
                return
            parsed, err = parse_int_strict(
                val, field_name=field, min_value=lo, max_value=hi
            )
            if err:
                validation_errors[field] = err
                return
            AppSetting.objects.update_or_create(
                key=key,
                defaults={"value": str(parsed), "value_type": "int"},
            )

        def _persist_float(key: str, field: str, lo: float, hi: float) -> None:
            val = data.get(field)
            if val is None:
                return
            parsed, err = parse_float_strict(
                val, field_name=field, min_value=lo, max_value=hi
            )
            if err:
                validation_errors[field] = err
                return
            AppSetting.objects.update_or_create(
                key=key,
                defaults={"value": str(parsed), "value_type": "float"},
            )

        _persist_bool("cooccurrence.enabled", "cooccurrence_enabled", True)
        _persist_int("cooccurrence.data_window_days", "data_window_days", 7, 365)
        _persist_int(
            "cooccurrence.min_co_session_count", "min_co_session_count", 1, 1000
        )
        _persist_float("cooccurrence.min_jaccard", "min_jaccard", 0.0, 1.0)
        _persist_float("cooccurrence.hub_min_jaccard", "hub_min_jaccard", 0.0, 1.0)
        _persist_int("cooccurrence.hub_min_members", "hub_min_members", 2, 100)
        _persist_bool(
            "cooccurrence.hub_detection_enabled", "hub_detection_enabled", True
        )
        _persist_bool("cooccurrence.schedule_weekly", "schedule_weekly", True)

        if validation_errors:
            # Some fields persisted, some failed validation. Return 400
            # so the operator sees which inputs were rejected; the saved
            # ones are reflected in the response body so the UI can
            # update partially-applied state.
            return Response(
                {
                    "detail": "Some fields could not be saved.",
                    "validation_errors": validation_errors,
                    "current_values": _read_cooccurrence_settings(),
                },
                status=400,
            )
        return Response(_read_cooccurrence_settings())
