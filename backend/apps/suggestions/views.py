"""
Suggestions app DRF viewsets.

Provides read + review actions for suggestions and pipeline runs.
The reviewer can approve, reject, or edit anchor text via the API.
The app NEVER writes to XenForo — all changes are to local records only.
"""

import logging
from datetime import datetime, timezone

from django.db.models import F
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, viewsets
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditEntry
from .models import PipelineDiagnostic, PipelineRun, Suggestion
from .serializers import (
    PipelineDiagnosticSerializer,
    PipelineRunSerializer,
    SuggestionDetailSerializer,
    SuggestionListSerializer,
    SuggestionReviewSerializer,
)

logger = logging.getLogger(__name__)


class PipelineRunViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve pipeline run history. Also provides a start action.

    GET  /api/pipeline-runs/         — paginated list
    GET  /api/pipeline-runs/{id}/    — full detail with progress
    POST /api/pipeline-runs/start/   — create and dispatch a new pipeline run
    """

    queryset = PipelineRun.objects.order_by("-created_at")
    serializer_class = PipelineRunSerializer
    filter_backends = [DjangoFilterBackend, filters.OrderingFilter]
    filterset_fields = ["run_state", "rerun_mode"]
    ordering_fields = ["created_at", "suggestions_created"]

    @action(detail=False, methods=["post"])
    def start(self, request) -> Response:
        """Create a new PipelineRun and dispatch it to Celery."""
        from apps.core.views import (
            get_field_aware_relevance_settings,
            get_learned_anchor_settings,
            get_phrase_matching_settings,
            get_rare_term_propagation_settings,
            get_weighted_authority_settings,
        )
        from apps.pipeline.services.algorithm_versions import (
            FIELD_AWARE_RELEVANCE_VERSION,
            LEARNED_ANCHOR_VERSION,
            PHRASE_MATCHING_VERSION,
            RARE_TERM_PROPAGATION_VERSION,
            WEIGHTED_AUTHORITY_VERSION,
        )

        run = PipelineRun.objects.create(
            rerun_mode=request.data.get("rerun_mode", "skip_pending"),
            host_scope=request.data.get("host_scope", {}),
            destination_scope=request.data.get("destination_scope", {}),
            config_snapshot={
                "weighted_authority": get_weighted_authority_settings(),
                "phrase_matching": get_phrase_matching_settings(),
                "learned_anchor": get_learned_anchor_settings(),
                "rare_term_propagation": get_rare_term_propagation_settings(),
                "field_aware_relevance": get_field_aware_relevance_settings(),
                "algorithm_versions": {
                    "weighted_authority": WEIGHTED_AUTHORITY_VERSION,
                    "phrase_matching": PHRASE_MATCHING_VERSION,
                    "learned_anchor": LEARNED_ANCHOR_VERSION,
                    "rare_term_propagation": RARE_TERM_PROPAGATION_VERSION,
                    "field_aware_relevance": FIELD_AWARE_RELEVANCE_VERSION,
                },
            },
        )
        from apps.pipeline.tasks import run_pipeline as _task
        _task.delay(
            run_id=str(run.run_id),
            host_scope=run.host_scope,
            destination_scope=run.destination_scope,
            rerun_mode=run.rerun_mode,
        )
        return Response(PipelineRunSerializer(run).data, status=status.HTTP_201_CREATED)


class SuggestionViewSet(viewsets.ModelViewSet):
    """
    List, retrieve, and review link suggestions.

    GET  /api/suggestions/               — paginated list with filters
    GET  /api/suggestions/{id}/          — full detail
    POST /api/suggestions/{id}/approve/  — approve a suggestion
    POST /api/suggestions/{id}/reject/   — reject a suggestion
    POST /api/suggestions/{id}/apply/    — mark as manually applied
    POST /api/suggestions/batch_action/  — approve/reject/skip many at once
    """

    queryset = (
        Suggestion.objects
        .select_related(
            "destination",
            "destination__scope",
            "destination__scope__silo_group",
            "host",
            "host__scope",
            "host__scope__silo_group",
            "host_sentence",
            "pipeline_run",
        )
        .order_by("-created_at")
    )
    filter_backends = [DjangoFilterBackend, filters.SearchFilter, filters.OrderingFilter]
    filterset_fields = ["status", "anchor_confidence", "repeated_anchor", "is_applied"]
    search_fields = ["destination_title", "host_sentence_text", "anchor_phrase"]
    ordering_fields = ["score_final", "created_at", "reviewed_at"]
    http_method_names = ["get", "post", "patch", "head", "options"]

    def get_serializer_class(self):
        if self.action in ("approve", "reject", "apply", "partial_update"):
            return SuggestionReviewSerializer
        if self.action == "retrieve":
            return SuggestionDetailSerializer
        return SuggestionListSerializer

    def get_queryset(self):
        queryset = super().get_queryset()
        same_silo = self.request.query_params.get("same_silo", "").strip().lower()
        if same_silo in {"1", "true", "yes"}:
            queryset = queryset.filter(
                destination__scope__silo_group__isnull=False,
                host__scope__silo_group__isnull=False,
                destination__scope__silo_group=F("host__scope__silo_group"),
            )
        return queryset

    # ── Review actions ────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None) -> Response:
        """Approve a pending suggestion. Optionally accepts anchor_edited."""
        suggestion = self.get_object()
        if suggestion.status not in ("pending", "rejected"):
            return Response(
                {"detail": f"Cannot approve a suggestion with status '{suggestion.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        suggestion.status = "approved"
        suggestion.reviewed_at = datetime.now(tz=timezone.utc)
        if "anchor_edited" in request.data:
            suggestion.anchor_edited = request.data["anchor_edited"]
        if "reviewer_notes" in request.data:
            suggestion.reviewer_notes = request.data["reviewer_notes"]
        suggestion.save(update_fields=["status", "reviewed_at", "anchor_edited", "reviewer_notes", "updated_at"])
        self._log_audit("approve", suggestion, request)
        return Response(SuggestionDetailSerializer(suggestion).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None) -> Response:
        """Reject a pending suggestion with an optional reason."""
        suggestion = self.get_object()
        if suggestion.status not in ("pending", "approved"):
            return Response(
                {"detail": f"Cannot reject a suggestion with status '{suggestion.status}'."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        suggestion.status = "rejected"
        suggestion.reviewed_at = datetime.now(tz=timezone.utc)
        suggestion.rejection_reason = request.data.get("rejection_reason", "")
        suggestion.reviewer_notes = request.data.get("reviewer_notes", "")
        suggestion.save(update_fields=["status", "reviewed_at", "rejection_reason", "reviewer_notes", "updated_at"])
        self._log_audit("reject", suggestion, request)
        return Response(SuggestionDetailSerializer(suggestion).data)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None) -> Response:
        """Mark an approved suggestion as manually applied on the live forum."""
        suggestion = self.get_object()
        if suggestion.status != "approved":
            return Response(
                {"detail": "Only approved suggestions can be marked as applied."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        suggestion.status = "applied"
        suggestion.is_applied = True
        suggestion.applied_at = datetime.now(tz=timezone.utc)
        suggestion.save(update_fields=["status", "is_applied", "applied_at", "updated_at"])
        self._log_audit("apply", suggestion, request)
        return Response(SuggestionDetailSerializer(suggestion).data)

    @action(detail=False, methods=["post"])
    def batch_action(self, request) -> Response:
        """
        Apply an action to multiple suggestions at once.

        Request body: {"action": "approve|reject|skip", "ids": ["uuid1", "uuid2", ...]}
        """
        action_name = request.data.get("action")
        ids = request.data.get("ids", [])

        if action_name not in ("approve", "reject", "skip"):
            return Response({"detail": "action must be 'approve', 'reject', or 'skip'."}, status=400)
        if not ids:
            return Response({"detail": "ids list is required."}, status=400)

        suggestions = Suggestion.objects.filter(suggestion_id__in=ids, status="pending")
        now = datetime.now(tz=timezone.utc)
        updated = 0

        for s in suggestions:
            if action_name == "approve":
                s.status = "approved"
                s.reviewed_at = now
            elif action_name == "reject":
                s.status = "rejected"
                s.reviewed_at = now
                s.rejection_reason = request.data.get("rejection_reason", "other")
            elif action_name == "skip":
                pass  # leave as pending, just skip in focus mode
            s.save(update_fields=["status", "reviewed_at", "rejection_reason", "updated_at"])
            updated += 1

        return Response({"updated": updated})

    # ── Internal helpers ──────────────────────────────────────────

    def _log_audit(self, action_name: str, suggestion: Suggestion, request) -> None:
        """Write an audit entry for a review action."""
        try:
            AuditEntry.objects.create(
                action=action_name,
                target_type="suggestion",
                target_id=str(suggestion.suggestion_id),
                detail={
                    "status": suggestion.status,
                    "rejection_reason": suggestion.rejection_reason,
                    "anchor_edited": suggestion.anchor_edited,
                    "score_final": suggestion.score_final,
                },
                ip_address=request.META.get("REMOTE_ADDR"),
            )
        except Exception:
            logger.exception("Failed to write audit entry for suggestion %s", suggestion.suggestion_id)


class PipelineDiagnosticViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List pipeline skip diagnostics for the 'why no suggestion?' explorer.

    GET /api/diagnostics/                    — all diagnostics
    GET /api/diagnostics/?pipeline_run={id}  — filter by run
    """

    queryset = PipelineDiagnostic.objects.select_related("destination", "pipeline_run")
    serializer_class = PipelineDiagnosticSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["pipeline_run", "skip_reason"]
