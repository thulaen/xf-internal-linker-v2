"""
Suggestions app DRF viewsets.

Provides read + review actions for suggestions and pipeline runs.
The reviewer can approve, reject, or edit anchor text via the API.
The app NEVER writes to XenForo — all changes are to local records only.
"""

import logging
from datetime import datetime, timezone

from django.db import transaction
from django.db.models import F
from django_filters.rest_framework import DjangoFilterBackend
from rest_framework import filters, status, views, viewsets
from rest_framework.permissions import IsAuthenticated
from rest_framework.decorators import action
from rest_framework.response import Response

from apps.audit.models import AuditEntry
from .models import (
    PipelineDiagnostic,
    PipelineRun,
    RankingChallenger,
    Suggestion,
    SuggestionPresentation,
    WeightAdjustmentHistory,
    WeightPreset,
)
from .serializers import (
    PipelineDiagnosticSerializer,
    PipelineRunSerializer,
    RankingChallengerSerializer,
    SuggestionDetailSerializer,
    SuggestionListSerializer,
    SuggestionReviewSerializer,
    WeightAdjustmentHistorySerializer,
    WeightPresetSerializer,
)
from .weight_preset_service import (
    apply_weights,
    get_current_weights,
    write_history,
)

logger = logging.getLogger(__name__)


class PipelineRunViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List and retrieve pipeline run history. Also provides a start action.

    GET  /api/pipeline-runs/         — paginated list
    GET  /api/pipeline-runs/{id}/    — full detail with progress
    POST /api/pipeline-runs/start/   — create and dispatch a new pipeline run
    """

    permission_classes = [IsAuthenticated]

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
        from apps.core.views_antispam import (
            get_anchor_diversity_settings,
            get_keyword_stuffing_settings,
            get_link_farm_settings,
        )
        from apps.core.runtime_registry import summarize_model_registry
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
                "anchor_diversity": get_anchor_diversity_settings(),
                "keyword_stuffing": get_keyword_stuffing_settings(),
                "link_farm": get_link_farm_settings(),
                "embedding_runtime": summarize_model_registry(),
                "algorithm_versions": {
                    "weighted_authority": WEIGHTED_AUTHORITY_VERSION,
                    "phrase_matching": PHRASE_MATCHING_VERSION,
                    "learned_anchor": LEARNED_ANCHOR_VERSION,
                    "rare_term_propagation": RARE_TERM_PROPAGATION_VERSION,
                    "field_aware_relevance": FIELD_AWARE_RELEVANCE_VERSION,
                },
            },
        )
        from apps.pipeline.tasks import dispatch_pipeline_run

        dispatch_pipeline_run(
            run_id=str(run.run_id),
            host_scope=run.host_scope,
            destination_scope=run.destination_scope,
            rerun_mode=run.rerun_mode,
        )
        return Response(PipelineRunSerializer(run).data, status=status.HTTP_201_CREATED)


class SuggestionViewSet(viewsets.ModelViewSet):
    """
    List, retrieve, and review link suggestions.
    """

    permission_classes = [IsAuthenticated]

    queryset = Suggestion.objects.select_related(
        "destination",
        "destination__scope",
        "destination__scope__silo_group",
        "host",
        "host__scope",
        "host__scope__silo_group",
        "host_sentence",
        "pipeline_run",
    ).order_by("-created_at")
    filter_backends = [
        DjangoFilterBackend,
        filters.SearchFilter,
        filters.OrderingFilter,
    ]
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

    def list(self, request, *args, **kwargs):
        """Override list to log suggestion presentations for exposure tracking.

        Each suggestion returned in the list response is recorded as
        "presented" to the requesting user. Deduplicated per user per day
        via a unique constraint on SuggestionPresentation.
        """
        response = super().list(request, *args, **kwargs)

        # Only log for authenticated, non-export requests
        if request.user and request.user.is_authenticated:
            suggestion_ids = [
                item.get("suggestion_id") or item.get("id")
                for item in (
                    response.data.get("results", [])
                    if isinstance(response.data, dict)
                    else response.data
                )
                if isinstance(item, dict)
            ]
            if suggestion_ids:
                today = datetime.now(tz=timezone.utc).date()
                presentations = [
                    SuggestionPresentation(
                        suggestion_id=sid,
                        user=request.user,
                        presented_date=today,
                    )
                    for sid in suggestion_ids
                    if sid is not None
                ]
                if presentations:
                    SuggestionPresentation.objects.bulk_create(
                        presentations, ignore_conflicts=True
                    )

        return response

    # ── Review actions ────────────────────────────────────────────

    @action(detail=True, methods=["post"])
    def approve(self, request, pk=None) -> Response:
        """Approve a pending suggestion. Optionally accepts anchor_edited."""
        suggestion = self.get_object()
        if suggestion.status not in ("pending", "rejected"):
            return Response(
                {
                    "detail": f"Cannot approve a suggestion with status '{suggestion.status}'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        suggestion.status = "approved"
        suggestion.reviewed_at = datetime.now(tz=timezone.utc)
        if "anchor_edited" in request.data:
            suggestion.anchor_edited = request.data["anchor_edited"]
        if "reviewer_notes" in request.data:
            suggestion.reviewer_notes = request.data["reviewer_notes"]
        suggestion.save(
            update_fields=[
                "status",
                "reviewed_at",
                "anchor_edited",
                "reviewer_notes",
                "updated_at",
            ]
        )
        self._log_audit("approve", suggestion, request)
        return Response(SuggestionDetailSerializer(suggestion).data)

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None) -> Response:
        """Reject a pending suggestion with an optional reason."""
        suggestion = self.get_object()
        if suggestion.status not in ("pending", "approved"):
            return Response(
                {
                    "detail": f"Cannot reject a suggestion with status '{suggestion.status}'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        suggestion.status = "rejected"
        suggestion.reviewed_at = datetime.now(tz=timezone.utc)
        suggestion.rejection_reason = request.data.get("rejection_reason", "")
        suggestion.reviewer_notes = request.data.get("reviewer_notes", "")
        suggestion.save(
            update_fields=[
                "status",
                "reviewed_at",
                "rejection_reason",
                "reviewer_notes",
                "updated_at",
            ]
        )
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
        suggestion.save(
            update_fields=["status", "is_applied", "applied_at", "updated_at"]
        )
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
            return Response(
                {"detail": "action must be 'approve', 'reject', or 'skip'."}, status=400
            )
        if not isinstance(ids, list):
            return Response({"detail": "ids must be a list."}, status=400)
        if len(ids) > 500:
            return Response({"detail": "Maximum 500 IDs per batch."}, status=400)
        if not ids:
            return Response({"detail": "ids list is required."}, status=400)

        suggestions = Suggestion.objects.filter(suggestion_id__in=ids, status="pending")
        now = datetime.now(tz=timezone.utc)
        if action_name == "approve":
            updated = suggestions.update(
                status="approved",
                reviewed_at=now,
                updated_at=now,
            )
        elif action_name == "reject":
            updated = suggestions.update(
                status="rejected",
                reviewed_at=now,
                rejection_reason=request.data.get("rejection_reason", "other"),
                updated_at=now,
            )
        else:
            updated = suggestions.update(updated_at=now)

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
            logger.exception(
                "Failed to write audit entry for suggestion %s",
                suggestion.suggestion_id,
            )


class PipelineDiagnosticViewSet(viewsets.ReadOnlyModelViewSet):
    """
    List pipeline skip diagnostics for the 'why no suggestion?' explorer.
    """

    permission_classes = [IsAuthenticated]

    queryset = PipelineDiagnostic.objects.select_related("destination", "pipeline_run")
    serializer_class = PipelineDiagnosticSerializer
    filter_backends = [DjangoFilterBackend]
    filterset_fields = ["pipeline_run", "skip_reason"]


class WeightPresetViewSet(viewsets.ModelViewSet):
    """
    CRUD for weight presets + apply action.
    """

    permission_classes = [IsAuthenticated]

    queryset = WeightPreset.objects.all()
    serializer_class = WeightPresetSerializer
    http_method_names = ["get", "post", "patch", "delete", "head", "options"]

    def update(self, request, *args, **kwargs):
        preset = self.get_object()
        if preset.is_system:
            return Response(
                {"detail": "System presets cannot be modified."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().update(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        kwargs["partial"] = True
        return self.update(request, *args, **kwargs)

    def destroy(self, request, *args, **kwargs):
        preset = self.get_object()
        if preset.is_system:
            return Response(
                {"detail": "System presets cannot be deleted."},
                status=status.HTTP_403_FORBIDDEN,
            )
        return super().destroy(request, *args, **kwargs)

    @action(detail=True, methods=["post"])
    def apply(self, request, pk=None):
        """Apply this preset's weights atomically to AppSetting and record history."""
        preset = self.get_object()

        previous_weights = get_current_weights()

        with transaction.atomic():
            apply_weights(preset.weights)

        new_weights = get_current_weights()
        username = (
            getattr(request.user, "username", "unknown") if request.user else "system"
        )
        write_history(
            source="preset_applied",
            previous_weights=previous_weights,
            new_weights=new_weights,
            reason=f"Preset: {preset.name} applied by {username}",
            preset=preset,
        )
        return Response({"detail": f"Preset '{preset.name}' applied successfully."})

    @action(detail=False, methods=["get"])
    def current(self, request):
        """Return the current in-scope AppSetting values as a weights dict."""
        return Response(get_current_weights())


class WeightAdjustmentHistoryViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only list of all weight adjustment events.
    """

    permission_classes = [IsAuthenticated]

    queryset = WeightAdjustmentHistory.objects.select_related("preset").order_by(
        "-created_at"
    )
    serializer_class = WeightAdjustmentHistorySerializer

    @action(detail=True, methods=["post"])
    def rollback(self, request, pk=None):
        """Roll back weights to the previous_weights snapshot of this history row."""
        history_row = self.get_object()
        target_weights = history_row.previous_weights

        previous_weights = get_current_weights()

        with transaction.atomic():
            apply_weights(target_weights)

        new_weights = get_current_weights()
        created_str = history_row.created_at.strftime("%Y-%m-%d %H:%M UTC")
        write_history(
            source="manual",
            previous_weights=previous_weights,
            new_weights=new_weights,
            reason=f"Rollback to {created_str}",
        )
        return Response({"detail": f"Rolled back to weights from {created_str}."})


class RankingChallengerViewSet(viewsets.ReadOnlyModelViewSet):
    """
    Read-only list of all RankingChallenger records.
    Also provides a POST /reject/ action for human override.
    """

    permission_classes = [IsAuthenticated]
    queryset = RankingChallenger.objects.order_by("-created_at")
    serializer_class = RankingChallengerSerializer

    @action(detail=True, methods=["post"])
    def reject(self, request, pk=None):
        challenger = self.get_object()
        if challenger.status != "pending":
            return Response(
                {
                    "detail": f"Cannot reject a challenger with status '{challenger.status}'."
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        challenger.status = "rejected"
        challenger.save(update_fields=["status", "updated_at"])
        return Response({"detail": f"Challenger {challenger.run_id[:16]} rejected."})


# ── FR-018: Internal write endpoint for C# auto-tuner ────────────────────────

# The four weights the C# L-BFGS optimizer is allowed to propose.
_TUNABLE_KEYS = frozenset({"w_semantic", "w_keyword", "w_node", "w_quality"})

# second line of defence).
_MAX_DELTA_PER_RUN = 0.05
_MAX_DRIFT_FROM_BASELINE = 0.20


class MetaAlgorithmSettingsView(views.APIView):
    """Phase MS — list every meta-algorithm with current runtime state.

    GET /api/meta-algorithms/

    Query params (optional):
      * `family` — filter by P1/P2/…/Q24/active/signal
      * `status` — filter by active/forward-declared/disabled
      * `q` — case-insensitive substring match on id/meta_code/title

    No new backend state: reads the registry (derived from existing
    `recommended_weights_phase2_*.py` files) and layers in current
    `AppSetting` values for `<algo>.enabled` + `<algo>.ranking_weight`.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.models import AppSetting

        from .meta_registry import enumerate_metas, families_summary

        metas = enumerate_metas()

        # Bulk-fetch AppSetting rows for the keys we care about so we
        # don't do 700+ single-row queries on a 375-entry list.
        wanted_keys: set[str] = set()
        for m in metas:
            wanted_keys.add(m.enabled_key)
            if m.weight_key:
                wanted_keys.add(m.weight_key)
        # Single batched query — materialise before iterating so the
        # N+1 detector doesn't flag the for/filter composition.
        setting_rows = list(
            AppSetting.objects.filter(key__in=list(wanted_keys)).values("key", "value")
        )
        setting_map: dict[str, str] = {row["key"]: row["value"] for row in setting_rows}

        rows: list[dict] = []
        for m in metas:
            enabled_raw = setting_map.get(m.enabled_key)
            enabled = _coerce_bool(enabled_raw)
            weight_val = setting_map.get(m.weight_key) if m.weight_key else None
            rows.append(
                {
                    "id": m.id,
                    "meta_code": m.meta_code,
                    "family": m.family,
                    "title": m.title,
                    "status": "disabled"
                    if enabled_raw is not None and not enabled
                    else m.status,
                    "enabled": enabled,
                    "enabled_key": m.enabled_key,
                    "weight_key": m.weight_key,
                    "weight_value": weight_val,
                    "spec_path": m.spec_path,
                    "cpp_kernel": m.cpp_kernel,
                    "param_keys": list(m.param_keys),
                }
            )

        # Apply query filters.
        family_filter = request.query_params.get("family", "").strip()
        status_filter = request.query_params.get("status", "").strip()
        query = request.query_params.get("q", "").strip().lower()

        if family_filter:
            rows = [r for r in rows if r["family"] == family_filter]
        if status_filter:
            rows = [r for r in rows if r["status"] == status_filter]
        if query:
            rows = [
                r
                for r in rows
                if query in r["id"].lower()
                or query in (r["meta_code"] or "").lower()
                or query in r["title"].lower()
            ]

        return Response(
            {
                "rows": rows,
                "families": families_summary(
                    type(
                        "ListWrap",
                        (),
                        {"__iter__": lambda self: iter(_MetasAdapter(rows))},
                    )()
                ),
                "total": len(rows),
            }
        )


class _MetasAdapter:
    """Tiny adapter so families_summary can iterate raw rows as if they
    were MetaDefinition instances (it only reads `.family` + `.status`)."""

    def __init__(self, rows):
        self._rows = rows

    def __iter__(self):
        class _Proxy:
            def __init__(self, row):
                self.family = row["family"]
                self.status = row["status"]

        return (_Proxy(r) for r in self._rows)


class MetaAlgorithmToggleView(views.APIView):
    """Phase MS — flip `<algo>.enabled` for a single meta-algorithm.

    POST /api/meta-algorithms/<id>/toggle/  body: {"enabled": true|false}

    Writes through to the AppSetting row (created if missing). Broadcasts
    on the `meta_algorithms.state` realtime topic so other operators see
    the change instantly.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, algo_id: str):
        from apps.core.models import AppSetting

        from .meta_registry import enumerate_metas

        # Validate the id is in the registry — refuse to create arbitrary
        # AppSetting rows via this endpoint.
        metas = {m.id: m for m in enumerate_metas()}
        meta = metas.get(algo_id)
        if meta is None:
            return Response(
                {"detail": f"unknown meta-algorithm id: {algo_id}"},
                status=status.HTTP_404_NOT_FOUND,
            )

        raw_enabled = request.data.get("enabled")
        if raw_enabled is None:
            return Response(
                {"detail": "body must include `enabled` (true/false)"},
                status=status.HTTP_400_BAD_REQUEST,
            )
        enabled = _coerce_bool(raw_enabled)
        new_value = "true" if enabled else "false"

        AppSetting.objects.update_or_create(
            key=meta.enabled_key,
            defaults={
                "value": new_value,
                "value_type": "bool",
                "category": "ml",
                "description": f"Auto-set by MetaAlgorithmToggleView for {meta.meta_code or meta.id}.",
            },
        )

        # Best-effort realtime nudge — every Settings tab viewer refreshes.
        try:
            from apps.realtime.services import broadcast

            broadcast(
                "meta_algorithms.state",
                "toggled",
                {
                    "id": meta.id,
                    "meta_code": meta.meta_code,
                    "enabled": enabled,
                },
            )
        except Exception:  # noqa: BLE001
            pass

        return Response(
            {
                "id": meta.id,
                "meta_code": meta.meta_code,
                "enabled": enabled,
            }
        )


def _coerce_bool(raw) -> bool:
    if isinstance(raw, bool):
        return raw
    if raw is None:
        return False
    s = str(raw).strip().lower()
    return s in {"1", "true", "yes", "on", "t", "y"}


class SuggestionReadinessView(views.APIView):
    """Phase SR — single endpoint the Review page consults before showing suggestions.

    Returns a compact `{ready, prerequisites, blocking, updated_at}` payload.
    Every prerequisite reuses an existing health / AppSetting source of truth;
    no new telemetry is introduced. Root-cause dedup is applied inside
    `apps.suggestions.readiness.assemble_prerequisites()`, so when the
    pipeline gate blocks, the operator sees one root explanation instead of
    five downstream echoes.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from .readiness import compute_readiness_payload

        return Response(compute_readiness_payload())
