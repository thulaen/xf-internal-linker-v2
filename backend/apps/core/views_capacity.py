"""
Jobs / helpers / optimization / user / analytics view layer extracted
from ``apps/core/views.py``.

Why this file exists
--------------------
``apps/core/views.py`` was the historical home of every view in the
core app and grew well past the 1500-line cap that ``CLAUDE.md`` (Code
Quality Mandate) targets. This is the **fourth** (and final) slice —
it pulls every job-queue + helper-PC + per-feature-optimisation +
user-auth + system-analytics view class out of ``views.py`` so the
mainline file can finally drop below the 1500-line cap and leave the
``.githooks/file-size-grandfather.txt`` list entirely.

Behaviour preserved exactly
---------------------------
This is a pure mechanical refactor. No request shape, validation rule,
or response payload changed. The original ``apps.core.views`` module
re-exports every class and helper defined in this file at the end of
``views.py`` so existing importers (``apps/core/urls.py``,
``apps/core/tests_dashboard_helpers.py``, ``apps.core.views_mcp``,
etc.) keep working unchanged via the ``from apps.core.views import …``
path they already use.

Helpers that remain in ``views.py``:
- The ``get_*_settings`` accessors (``get_click_distance_settings``,
  ``get_clustering_settings``, ``get_feedback_rerank_settings``,
  ``get_slate_diversity_settings``, ``get_graph_candidate_settings``,
  ``get_value_model_settings``) — used by the moved views *and* by
  callers outside the core app, so they have to live with their
  ``_read_*`` companions in ``views.py``.
- The ``_validate_click_distance_settings``,
  ``_validate_feedback_rerank_settings``, and
  ``_validate_clustering_settings`` validators — each is reused by
  its ``get_*_settings`` accessor's "clamp don't reject" fallback,
  so they must stay where the accessors are.

This file owns every helper used **only** by the moved view classes:
the heartbeat field-group helpers, the job-queue + quarantine
formatters, the spam-guard / graph-candidate / value-model row
builders + bound dicts, and the localhost-only setup gate.
"""

from __future__ import annotations

import logging
import uuid

from django.conf import settings as django_settings
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.query_params import coerce_bool, coerce_float, coerce_int
from apps.api.throttles import (
    ChallengerEvalThrottle as _ChallengerEvalThrottle,
    CompressionAuditRunThrottle,
    GraphRebuildThrottle as _GraphRebuildThrottle,
    PerformanceCertRunThrottle,
    WeightRecalcThrottle as _WeightRecalcThrottle,
)
from apps.core.services.settings_helpers import (
    coerce_clamp_float,
    coerce_clamp_int,
    coerce_lenient_bool,
    read_app_setting_int,
)
from apps.core.views_settings import _format_setting_value

logger = logging.getLogger(__name__)


# ── Job queue helpers ─────────────────────────────────────────────


def _job_queue_active_runs() -> list[dict]:
    """Active + queued PipelineRun rows formatted for the queue panel."""
    from apps.pipeline.services.eta_estimator import estimate_eta
    from apps.suggestions.models import PipelineRun

    runs = list(
        PipelineRun.objects.filter(run_state__in=["queued", "running"])
        .values(
            "run_id",
            "run_state",
            "rerun_mode",
            "suggestions_created",
            "destinations_processed",
            "phase_log",
            "celery_task_id",
            "created_at",
            "updated_at",
        )
        .order_by("created_at")[:20]
    )
    for run in runs:
        run["run_id"] = str(run["run_id"])
        run["type"] = "pipeline"
        if run["created_at"]:
            run["created_at"] = run["created_at"].isoformat()
        if run["updated_at"]:
            run["updated_at"] = run["updated_at"].isoformat()
        eta = estimate_eta("pipeline.run_pipeline")
        run["estimated_remaining_seconds"] = eta.total_seconds() if eta else None
    return runs


def _job_queue_active_syncs() -> list[dict]:
    """Active + queued SyncJob rows formatted for the queue panel."""
    from apps.pipeline.services.eta_estimator import estimate_eta
    from apps.sync.models import SyncJob

    jobs = list(
        SyncJob.objects.filter(status__in=["pending", "running", "paused"])
        .values(
            "job_id",
            "status",
            "source",
            "mode",
            "progress",
            "items_synced",
            "checkpoint_stage",
            "is_resumable",
            "created_at",
            "started_at",
        )
        .order_by("created_at")[:20]
    )
    for job in jobs:
        job["job_id"] = str(job["job_id"])
        job["type"] = "sync"
        if job["created_at"]:
            job["created_at"] = job["created_at"].isoformat()
        if job["started_at"]:
            job["started_at"] = job["started_at"].isoformat()
        eta = estimate_eta("nightly-xenforo-sync", mode=job.get("mode"))
        job["estimated_remaining_seconds"] = eta.total_seconds() if eta else None
    return jobs


class JobQueueView(APIView):
    """GET /api/jobs/queue/ — active and queued tasks with ETA and lock status."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Active + queued tasks across pipeline + sync, plus active locks.

        Refactored 2026-05-04: was 67 lines. Each source list is now its
        own helper that returns dicts already in the canonical response
        shape. The ``items`` array preserves the original "pipeline runs
        first, then sync jobs" ordering.
        """
        from apps.pipeline.services.task_lock import get_active_locks

        return Response(
            {
                "items": (_job_queue_active_runs() + _job_queue_active_syncs()),
                "locks": get_active_locks(),
            }
        )


# ── JobQuarantineView helpers (extracted from .get) ──────────────


def _quarantine_records_and_run_ids() -> tuple[list[dict], set[str]]:
    """New-style: open ``QuarantineRecord`` rows.

    Returns ``(records, quarantined_run_ids)`` so the legacy fold-in
    helper can dedup against rows already covered by a record.
    """
    from apps.core.models import QuarantineRecord

    open_records = QuarantineRecord.objects.filter(resolved_at__isnull=True).order_by(
        "-updated_at"
    )[:50]
    records: list[dict] = []
    quarantined_run_ids: set[str] = set()
    for rec in open_records:
        records.append(
            {
                "id": rec.pk,
                "kind": "record",
                "run_id": rec.related_object_id,
                "related_object_type": rec.related_object_type,
                "reason": rec.reason,
                "reason_display": rec.get_reason_display(),
                "reason_detail": rec.reason_detail,
                "affected_items": rec.affected_items,
                "fix_available": rec.fix_available,
                "resume_from_checkpoint": rec.resume_from_checkpoint,
                "checkpoint_id": rec.checkpoint_id,
                "created_at": rec.created_at.isoformat(),
                "updated_at": rec.updated_at.isoformat(),
            }
        )
        if rec.related_object_type == "pipeline_run":
            quarantined_run_ids.add(rec.related_object_id)
    return records, quarantined_run_ids


def _quarantine_legacy_rows(*, skip_run_ids: set[str]) -> list[dict]:
    """Legacy: ``PipelineRun.is_quarantined=True`` rows without a matching record.

    The ``skip_run_ids`` set lets the caller exclude legacy rows that
    are already represented in the new ``QuarantineRecord`` table —
    preserves the dedup contract from the original 76-line handler.
    """
    from apps.suggestions.models import PipelineRun

    legacy_runs = list(
        PipelineRun.objects.filter(is_quarantined=True)
        .values(
            "run_id",
            "run_state",
            "rerun_mode",
            "error_message",
            "phase_log",
            "created_at",
            "updated_at",
        )
        .order_by("-updated_at")[:50]
    )
    rows: list[dict] = []
    for run in legacy_runs:
        rid = str(run["run_id"])
        if rid in skip_run_ids:
            continue
        rows.append(_legacy_quarantine_row(run, rid))
    return rows


def _legacy_quarantine_row(run: dict, rid: str) -> dict:
    """Build one legacy-quarantine dict in the canonical response shape."""
    return {
        "id": None,
        "kind": "legacy",
        "run_id": rid,
        "related_object_type": "pipeline_run",
        "reason": "repeated_failure",
        "reason_display": "Repeated failures",
        "reason_detail": run.get("error_message") or "",
        "affected_items": [],
        "fix_available": "reset-quarantined-job",
        "resume_from_checkpoint": False,
        "checkpoint_id": "",
        "run_state": run["run_state"],
        "rerun_mode": run["rerun_mode"],
        "phase_log": run["phase_log"],
        "created_at": run["created_at"].isoformat() if run["created_at"] else None,
        "updated_at": run["updated_at"].isoformat() if run["updated_at"] else None,
    }


class JobQuarantineView(APIView):
    """GET /api/jobs/quarantine/ — quarantined items (first-class model, plan item 16).

    Prefers the new `QuarantineRecord` table; for back-compat also folds in any
    `PipelineRun.is_quarantined=True` rows that don't have a matching
    QuarantineRecord yet.  Frontend reads from the same endpoint; no breaking
    change.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Combined open-quarantine list — new QuarantineRecord rows + legacy.

        Refactored 2026-05-04: was 76 lines. Each source (new + legacy)
        is now its own helper so the merge logic is testable in
        isolation. The dedup-by-run_id rule is preserved exactly.
        """
        records, quarantined_run_ids = _quarantine_records_and_run_ids()
        legacy = _quarantine_legacy_rows(skip_run_ids=quarantined_run_ids)
        return Response(records + legacy)


class HelperNodeListView(APIView):
    """GET/POST /api/settings/helpers/ — list and register helper nodes."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.models import HelperNode
        from apps.core.views_runtime_registry import serialize_helper_node

        nodes = HelperNode.objects.all()
        data = [serialize_helper_node(n) for n in nodes]
        return Response(data)

    def post(self, request):
        import hashlib

        from apps.core.models import HelperNode

        name = request.data.get("name")
        token = request.data.get("token")
        if not name or not token:
            return Response({"error": "name and token are required"}, status=400)

        token_hash = hashlib.sha256(token.encode()).hexdigest()
        node, created = HelperNode.objects.get_or_create(
            name=name,
            defaults={
                "token_hash": token_hash,
                "role": request.data.get("role", "worker"),
                "capabilities": request.data.get("capabilities", {}),
                "allowed_queues": request.data.get("allowed_queues", []),
                "allowed_job_types": request.data.get("allowed_job_types", []),
                "time_policy": request.data.get("time_policy", "anytime"),
                "max_concurrency": request.data.get("max_concurrency", 2),
                "cpu_cap_pct": request.data.get("cpu_cap_pct", 60),
                "ram_cap_pct": request.data.get("ram_cap_pct", 60),
                "accepting_work": bool(request.data.get("accepting_work", True)),
            },
        )
        if not created:
            return Response(
                {"error": "A node with this name already exists"}, status=409
            )

        return Response({"id": node.id, "name": node.name}, status=201)


class HelperNodeDetailView(APIView):
    """PATCH/DELETE /api/settings/helpers/<id>/ — update or remove a helper node."""

    permission_classes = [IsAuthenticated]

    def patch(self, request, pk):
        import hashlib

        from apps.core.models import HelperNode
        from apps.core.views_runtime_registry import serialize_helper_node

        try:
            node = HelperNode.objects.get(pk=pk)
        except HelperNode.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        for field in (
            "role",
            "status",
            "time_policy",
            "max_concurrency",
            "cpu_cap_pct",
            "ram_cap_pct",
            "accepting_work",
            "active_jobs",
            "queued_jobs",
            "cpu_pct",
            "ram_pct",
            "gpu_util_pct",
            "gpu_vram_used_mb",
            "gpu_vram_total_mb",
            "network_rtt_ms",
            "native_kernels_healthy",
        ):
            if field in request.data:
                setattr(node, field, request.data[field])
        for json_field in (
            "capabilities",
            "allowed_queues",
            "allowed_job_types",
            "warmed_model_keys",
        ):
            if json_field in request.data:
                setattr(node, json_field, request.data[json_field])
        token = request.data.get("token")
        if token:
            node.token_hash = hashlib.sha256(str(token).encode()).hexdigest()
        node.save()
        return Response(serialize_helper_node(node))

    def delete(self, request, pk):
        from apps.core.models import HelperNode

        deleted, _ = HelperNode.objects.filter(pk=pk).delete()
        if not deleted:
            return Response({"error": "Not found"}, status=404)
        return Response(status=204)


# ── Heartbeat helpers (extracted from HelperNodeHeartbeatView.post) ──
# Each helper mutates the in-memory HelperNode, leaving persistence to
# the caller. Splitting per field group keeps the main handler small +
# makes each defensive coercion independently testable.

# Save fields list — single source of truth so adding a new field
# updates the helper AND the caller's update_fields=[...] list together.
_HEARTBEAT_UPDATE_FIELDS = (
    "last_heartbeat",
    "last_snapshot_at",
    "status",
    "capabilities",
    "accepting_work",
    "active_jobs",
    "queued_jobs",
    "cpu_pct",
    "ram_pct",
    "gpu_util_pct",
    "gpu_vram_used_mb",
    "gpu_vram_total_mb",
    "network_rtt_ms",
    "native_kernels_healthy",
    "warmed_model_keys",
    "updated_at",
)


def _apply_heartbeat_identity(node, data: dict) -> None:
    """Apply non-numeric identity fields: status enum + capabilities + accepting_work.

    Defensive type checks: status restricted to documented enum,
    accepting_work routed through ``coerce_bool`` so non-bool truthy
    inputs ("yes", 1) parse correctly without silently flipping
    operators trying to disable a feature via curl.
    """
    from apps.core.models import HelperNode

    if "status" in data:
        raw_status = data["status"]
        if (
            isinstance(raw_status, str)
            and raw_status in HelperNode.VALID_HEARTBEAT_STATUSES
        ):
            node.status = raw_status
    if "capabilities" in data and isinstance(data["capabilities"], dict):
        merged = dict(node.capabilities or {})
        merged.update(data["capabilities"])
        node.capabilities = merged
    if "accepting_work" in data:
        raw_accepting = data["accepting_work"]
        if isinstance(raw_accepting, (bool, int, float, str)):
            node.accepting_work = coerce_bool(
                raw_accepting, default=node.accepting_work
            )


def _apply_heartbeat_load_metrics(node, data: dict) -> None:
    """Apply CPU + queue-depth metrics with defensive int / float clamps."""
    if "active_jobs" in data:
        node.active_jobs = coerce_int(
            data["active_jobs"], default=node.active_jobs, min_value=0
        )
    if "queued_jobs" in data:
        node.queued_jobs = coerce_int(
            data["queued_jobs"], default=node.queued_jobs, min_value=0
        )
    if "cpu_pct" in data:
        node.cpu_pct = coerce_float(
            data["cpu_pct"],
            default=node.cpu_pct or 0.0,
            min_value=0.0,
            max_value=100.0,
        )
    if "ram_pct" in data:
        node.ram_pct = coerce_float(
            data["ram_pct"],
            default=node.ram_pct or 0.0,
            min_value=0.0,
            max_value=100.0,
        )


def _apply_heartbeat_gpu_metrics(node, data: dict) -> None:
    """Apply GPU utilisation + VRAM metrics. Empty / null clears the field."""
    if "gpu_util_pct" in data:
        gpu_util = data["gpu_util_pct"]
        node.gpu_util_pct = (
            None
            if gpu_util in ("", None)
            else coerce_float(
                gpu_util,
                default=node.gpu_util_pct or 0.0,
                min_value=0.0,
                max_value=100.0,
            )
        )
    if "gpu_vram_used_mb" in data:
        gpu_vram_used = data["gpu_vram_used_mb"]
        node.gpu_vram_used_mb = (
            None
            if gpu_vram_used in ("", None)
            else coerce_int(
                gpu_vram_used, default=node.gpu_vram_used_mb or 0, min_value=0
            )
        )
    if "gpu_vram_total_mb" in data:
        gpu_vram_total = data["gpu_vram_total_mb"]
        node.gpu_vram_total_mb = (
            None
            if gpu_vram_total in ("", None)
            else coerce_int(
                gpu_vram_total, default=node.gpu_vram_total_mb or 0, min_value=0
            )
        )


def _apply_heartbeat_network_health(node, data: dict) -> None:
    """Apply network RTT + kernel health + warmed-model-keys list."""
    if "network_rtt_ms" in data:
        rtt = data["network_rtt_ms"]
        node.network_rtt_ms = (
            None
            if rtt in ("", None)
            else coerce_int(rtt, default=node.network_rtt_ms or 0, min_value=0)
        )
    if "native_kernels_healthy" in data:
        node.native_kernels_healthy = bool(data["native_kernels_healthy"])
    if "warmed_model_keys" in data and isinstance(data["warmed_model_keys"], list):
        node.warmed_model_keys = data["warmed_model_keys"]


class HelperNodeHeartbeatView(APIView):
    """POST /api/settings/helpers/<id>/heartbeat/

    Stub endpoint for helper nodes to report liveness. Updates
    ``last_heartbeat`` and optionally merges ``capabilities`` and updates
    ``status``. Returns 204 on success.

    The helper-client side that calls this endpoint is forward-looking
    (Stage 8 / multi-node). The endpoint exists so docs/PERFORMANCE.md §2
    is not lying about it and so the next session that wires up the helper
    client has a real route to POST to.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        """Accept one helper-PC heartbeat payload + persist any updated fields.

        Refactored 2026-05-04: was 138 lines. Each field group is now a
        per-domain helper (``_apply_heartbeat_*``) so the handler stays
        small, the per-field defensive logic is reusable, and each helper
        can be unit-tested without spinning up the full request lifecycle.
        Behaviour preserved exactly — every defensive type check + range
        clamp survives unchanged.
        """
        from django.utils import timezone

        from apps.core.models import HelperNode

        try:
            node = HelperNode.objects.get(pk=pk)
        except HelperNode.DoesNotExist:
            return Response({"error": "Not found"}, status=404)

        node.last_heartbeat = timezone.now()
        node.last_snapshot_at = timezone.now()
        _apply_heartbeat_identity(node, request.data)
        _apply_heartbeat_load_metrics(node, request.data)
        _apply_heartbeat_gpu_metrics(node, request.data)
        _apply_heartbeat_network_health(node, request.data)
        node.save(update_fields=_HEARTBEAT_UPDATE_FIELDS)
        return Response(status=204)


class ClickDistanceSettingsView(APIView):
    """
    GET /api/settings/click-distance/
    PUT /api/settings/click-distance/
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_click_distance_settings

        return Response(get_click_distance_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import (
            _validate_click_distance_settings,
            get_click_distance_settings,
        )

        current = get_click_distance_settings()
        try:
            validated = _validate_click_distance_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        for key, value in validated.items():
            AppSetting.objects.update_or_create(
                key=f"click_distance.{key}", defaults={"value": str(value)}
            )

        return Response(validated)


class ClickDistanceRecalculateView(APIView):
    """
    POST /api/settings/click-distance/recalculate/
    """

    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        """Trigger bulk recalculation of click distance scores."""
        from apps.pipeline.tasks import recalculate_click_distance_task

        task = recalculate_click_distance_task.delay()
        return Response({"status": "queued", "job_id": task.id})


class FeedbackRerankSettingsView(APIView):
    """
    GET  /api/settings/explore-exploit/ - returns FR-013 explore/exploit settings
    PUT  /api/settings/explore-exploit/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_feedback_rerank_settings

        return Response(get_feedback_rerank_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import (
            _validate_feedback_rerank_settings,
            get_feedback_rerank_settings,
        )

        current = get_feedback_rerank_settings()
        try:
            validated = _validate_feedback_rerank_settings(
                request.data, current=current
            )
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "explore_exploit.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether feedback-driven explore/exploit reranking is active.",
            },
            "explore_exploit.ranking_weight": {
                "value": str(validated["ranking_weight"]),
                "value_type": "float",
                "description": "Multiplier weight for the feedback-driven score component.",
            },
            "explore_exploit.exploration_rate": {
                "value": str(validated["exploration_rate"]),
                "value_type": "float",
                "description": "k factor for the UCB1 exploration boost.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )

        return Response(validated)


class ClusteringSettingsView(APIView):
    """
    GET  /api/settings/clustering/ - returns FR-014 clustering configuration
    PUT  /api/settings/clustering/ - validates and persists clustering configuration
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_clustering_settings

        return Response(get_clustering_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import (
            _validate_clustering_settings,
            get_clustering_settings,
        )

        current = get_clustering_settings()
        try:
            validated = _validate_clustering_settings(request.data, current)
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        rows = {
            "clustering.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether to cluster near-duplicate destinations and suppress non-canonicals.",
            },
            "clustering.similarity_threshold": {
                "value": str(validated["similarity_threshold"]),
                "value_type": "float",
                "description": "Cosine distance threshold for near-duplicate grouping (lower = stricter).",
            },
            "clustering.suppression_penalty": {
                "value": str(validated["suppression_penalty"]),
                "value_type": "float",
                "description": "Fixed score penalty applied to non-canonical cluster members.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class ClusteringRecalculateView(APIView):
    """POST /api/settings/clustering/recalculate/ - run batch clustering pass."""

    throttle_classes = [_WeightRecalcThrottle]

    def post(self, request):
        from apps.pipeline.tasks import run_clustering_pass

        job_id = str(uuid.uuid4())
        run_clustering_pass.delay(job_id=job_id)
        return Response({"job_id": job_id}, status=202)


# ── Slate-diversity validator (only used by the view class below) ─


def _validate_slate_diversity_settings(payload: dict, current: dict) -> dict:
    """Validate and clamp slate diversity settings."""
    from apps.core.services.settings_helpers import DEFAULT_SLATE_DIVERSITY_SETTINGS

    def _get_float(key: str) -> float:
        val = payload.get(key, current.get(key))
        try:
            return float(val)
        except (TypeError, ValueError):
            return float(current.get(key, DEFAULT_SLATE_DIVERSITY_SETTINGS[key]))

    def _get_bool(key: str) -> bool:
        val = payload.get(key, current.get(key))
        return coerce_bool(val, default=False)

    return {
        "enabled": _get_bool("enabled"),
        "diversity_lambda": max(0.0, min(1.0, _get_float("diversity_lambda"))),
        "score_window": max(0.05, min(1.0, _get_float("score_window"))),
        "similarity_cap": max(0.70, min(0.99, _get_float("similarity_cap"))),
        "algorithm_version": DEFAULT_SLATE_DIVERSITY_SETTINGS["algorithm_version"],
    }


class SlateDiversitySettingsView(APIView):
    """
    GET  /api/settings/slate-diversity/ - returns FR-015 slate diversity settings
    PUT  /api/settings/slate-diversity/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_slate_diversity_settings

        return Response(get_slate_diversity_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import get_slate_diversity_settings

        current = get_slate_diversity_settings()
        try:
            validated = _validate_slate_diversity_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        rows = {
            "slate_diversity.enabled": {
                "value": "true" if validated["enabled"] else "false",
                "value_type": "bool",
                "description": "Whether FR-015 MMR slate diversity reranking is active.",
            },
            "slate_diversity.diversity_lambda": {
                "value": str(validated["diversity_lambda"]),
                "value_type": "float",
                "description": "MMR lambda: 1.0 = pure relevance, 0.0 = pure diversity.",
            },
            "slate_diversity.score_window": {
                "value": str(validated["score_window"]),
                "value_type": "float",
                "description": "Max score gap from top candidate for MMR eligibility.",
            },
            "slate_diversity.similarity_cap": {
                "value": str(validated["similarity_cap"]),
                "value_type": "float",
                "description": "Cosine similarity above which two destinations are flagged as redundant.",
            },
        }

        for key, row in rows.items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )

        return Response(validated)


class WeightTuneTriggerView(APIView):
    """POST /api/settings/weight-tune/trigger/ — manually trigger a FR-018 weight-tune run."""

    permission_classes = [IsAuthenticated]

    def post(self, request):
        from apps.pipeline.tasks import monthly_weight_tune

        task = monthly_weight_tune.delay()
        return Response(
            {"detail": "Weight-tune task queued.", "task_id": task.id}, status=202
        )


class ChallengerEvaluateView(APIView):
    """POST /api/settings/weight-tune/evaluate/<run_id>/ — manually evaluate a pending challenger."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [_ChallengerEvalThrottle]

    def post(self, request, run_id):
        from apps.pipeline.tasks import evaluate_weight_challenger
        from apps.suggestions.models import RankingChallenger

        if not RankingChallenger.objects.filter(
            run_id=run_id, status="pending"
        ).exists():
            return Response(
                {"detail": f"No pending challenger with run_id '{run_id}'."},
                status=404,
            )

        task = evaluate_weight_challenger.delay(run_id=run_id)
        return Response(
            {"detail": "Evaluation queued.", "task_id": task.id}, status=202
        )


# ── Graph-candidate row spec, validator, and view ────────────────


# (validated_key, setting_key, value_type, description) for graph-candidate rows.
_GRAPH_CANDIDATE_ROW_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (
        "enabled",
        "graph_candidate.enabled",
        "bool",
        "Whether FR-021 Pixie walk candidate generation is active.",
    ),
    (
        "walk_steps_per_entity",
        "graph_candidate.walk_steps_per_entity",
        "int",
        "Number of Pixie random walk steps to perform per query entity.",
    ),
    (
        "min_stable_candidates",
        "graph_candidate.min_stable_candidates",
        "int",
        "Minimum number of stable candidates to find before early stopping.",
    ),
    (
        "min_visit_threshold",
        "graph_candidate.min_visit_threshold",
        "int",
        "Minimum walk visits required for a node to be considered stable.",
    ),
    (
        "top_k_candidates",
        "graph_candidate.top_k_candidates",
        "int",
        "Max number of top-visited candidates to return to the pipeline.",
    ),
    (
        "top_n_entities_per_article",
        "graph_candidate.top_n_entities_per_article",
        "int",
        "Max number of top entities to extract per article for graph linking.",
    ),
)


def _build_graph_candidate_rows(validated: dict) -> dict[str, dict]:
    """Pure function — turn a validated graph-candidate dict into AppSetting rows."""
    return {
        setting_key: {
            "value": _format_setting_value(validated[validated_key], value_type),
            "value_type": value_type,
            "description": description,
        }
        for validated_key, setting_key, value_type, description in _GRAPH_CANDIDATE_ROW_SPEC
    }


_GRAPH_CANDIDATE_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "walk_steps_per_entity": (10, 10000),
    "min_stable_candidates": (5, 500),
    "min_visit_threshold": (1, 20),
    "top_k_candidates": (10, 1000),
    "top_n_entities_per_article": (1, 100),
}


def _validate_graph_candidate_settings(payload: dict, current: dict) -> dict:
    out: dict = {"enabled": coerce_lenient_bool(payload, current, "enabled")}
    for key, (lo, hi) in _GRAPH_CANDIDATE_INT_BOUNDS.items():
        out[key] = coerce_clamp_int(payload, current, key, lo, hi)
    return out


class GraphCandidateSettingsView(APIView):
    """
    GET  /api/settings/graph-candidate/ - returns FR-021 graph-walk settings
    PUT  /api/settings/graph-candidate/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_graph_candidate_settings

        return Response(get_graph_candidate_settings())

    def put(self, request):
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import get_graph_candidate_settings

        current = get_graph_candidate_settings()
        try:
            validated = _validate_graph_candidate_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        for key, row in _build_graph_candidate_rows(validated).items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


# ── Value-model row builders, bounds, validator, view ────────────


def _vm_bool_str(v: object) -> str:
    """Bool → "true"/"false" — single source for value-model rows."""
    return "true" if v else "false"


def _build_value_model_rows(validated: dict) -> dict[str, dict[str, str]]:
    """Pure function — turn a validated value-model dict into AppSetting rows.

    Each entry maps an AppSetting key to ``{value, value_type, description}``.
    The body is split into per-feature-area helpers so the table data
    stays scannable while no single function exceeds the 50-line lint
    budget. Tests pin every serialisation rule + the "every input key
    produces a row" invariant.
    """
    return {
        **_vm_rows_core(validated),
        **_vm_rows_engagement(validated),
        **_vm_rows_hot_decay(validated),
        **_vm_rows_co_occurrence(validated),
    }


def _vm_rows_core(validated: dict) -> dict[str, dict[str, str]]:
    """FR-021 base value-model: enabled flag + 5 component weights + traffic."""
    return {
        "value_model.enabled": {
            "value": _vm_bool_str(validated["enabled"]),
            "value_type": "bool",
            "description": "Whether FR-021 Instagram-style value pre-scoring is active.",
        },
        "value_model.w_relevance": {
            "value": str(validated["w_relevance"]),
            "value_type": "float",
            "description": "Value component weight: semantic relevance.",
        },
        "value_model.w_traffic": {
            "value": str(validated["w_traffic"]),
            "value_type": "float",
            "description": "Value component weight: historical traffic.",
        },
        "value_model.w_freshness": {
            "value": str(validated["w_freshness"]),
            "value_type": "float",
            "description": "Value component weight: content freshness.",
        },
        "value_model.w_authority": {
            "value": str(validated["w_authority"]),
            "value_type": "float",
            "description": "Value component weight: content authority.",
        },
        "value_model.w_penalty": {
            "value": str(validated["w_penalty"]),
            "value_type": "float",
            "description": "Value component weight: blocklist/penalty sink.",
        },
        "value_model.traffic_lookback_days": {
            "value": str(validated["traffic_lookback_days"]),
            "value_type": "int",
            "description": "Number of days of traffic history to look back.",
        },
        "value_model.traffic_fallback_value": {
            "value": str(validated["traffic_fallback_value"]),
            "value_type": "float",
            "description": "Default traffic score to use if no data exists.",
        },
    }


def _vm_rows_engagement(validated: dict) -> dict[str, dict[str, str]]:
    """FR-024 engagement / read-through rate signal."""
    return {
        "value_model.engagement_signal_enabled": {
            "value": _vm_bool_str(validated["engagement_signal_enabled"]),
            "value_type": "bool",
            "description": "Whether FR-024 engagement (read-through rate) signal is active.",
        },
        "value_model.w_engagement": {
            "value": str(validated["w_engagement"]),
            "value_type": "float",
            "description": "Value component weight: engagement / read-through rate signal.",
        },
        "value_model.engagement_lookback_days": {
            "value": str(validated["engagement_lookback_days"]),
            "value_type": "int",
            "description": "Rolling window (days) for averaging SearchMetric engagement rows.",
        },
        "value_model.engagement_words_per_minute": {
            "value": str(validated["engagement_words_per_minute"]),
            "value_type": "int",
            "description": "WPM constant used to estimate article read time.",
        },
        "value_model.engagement_cap_ratio": {
            "value": str(validated["engagement_cap_ratio"]),
            "value_type": "float",
            "description": "Cap applied to raw read-through rate before site-wide normalization.",
        },
        "value_model.engagement_fallback_value": {
            "value": str(validated["engagement_fallback_value"]),
            "value_type": "float",
            "description": "Fallback signal value when no SearchMetric rows exist for a destination.",
        },
    }


def _vm_rows_hot_decay(validated: dict) -> dict[str, dict[str, str]]:
    """FR-023 Reddit-style hot-decay signal."""
    return {
        "value_model.hot_decay_enabled": {
            "value": _vm_bool_str(validated["hot_decay_enabled"]),
            "value_type": "bool",
            "description": "Whether FR-023 Reddit Hot decay replaces flat traffic averaging.",
        },
        "value_model.hot_gravity": {
            "value": str(validated["hot_gravity"]),
            "value_type": "float",
            "description": "Time-decay gravity factor for the Reddit Hot formula.",
        },
        "value_model.hot_clicks_weight": {
            "value": str(validated["hot_clicks_weight"]),
            "value_type": "float",
            "description": "Weight applied to click volume in hot score calculation.",
        },
        "value_model.hot_impressions_weight": {
            "value": str(validated["hot_impressions_weight"]),
            "value_type": "float",
            "description": "Weight applied to impression volume in hot score calculation.",
        },
        "value_model.hot_lookback_days": {
            "value": str(validated["hot_lookback_days"]),
            "value_type": "int",
            "description": "Number of days of daily traffic data to feed into hot scoring.",
        },
    }


def _vm_rows_co_occurrence(validated: dict) -> dict[str, dict[str, str]]:
    """FR-025 session co-occurrence signal."""
    return {
        "value_model.co_occurrence_signal_enabled": {
            "value": _vm_bool_str(validated["co_occurrence_signal_enabled"]),
            "value_type": "bool",
            "description": "Whether the FR-025 session co-occurrence signal is active.",
        },
        "value_model.w_cooccurrence": {
            "value": str(validated["w_cooccurrence"]),
            "value_type": "float",
            "description": "Value component weight: session co-occurrence signal.",
        },
        "value_model.co_occurrence_fallback_value": {
            "value": str(validated["co_occurrence_fallback_value"]),
            "value_type": "float",
            "description": "Fallback signal value when no co-occurrence pair exists.",
        },
        "value_model.co_occurrence_min_co_sessions": {
            "value": str(validated["co_occurrence_min_co_sessions"]),
            "value_type": "int",
            "description": "Minimum co-session count for a pair to be used in scoring.",
        },
    }


# Per-key (lo, hi) for the value-model settings.
# Spec is "clamp don't reject" so out-of-range values silently become the
# nearest endpoint via coerce_clamp_*. Adding a new value-model knob =
# add the key here + one line in the helper below.
_VALUE_MODEL_FLOAT_BOUNDS: dict[str, tuple[float, float]] = {
    "w_relevance": (0.0, 1.0),
    "w_traffic": (0.0, 1.0),
    "w_freshness": (0.0, 1.0),
    "w_authority": (0.0, 1.0),
    "w_penalty": (0.0, 1.0),
    "traffic_fallback_value": (0.0, 1.0),
    "w_engagement": (0.0, 1.0),
    "engagement_cap_ratio": (1.0, 5.0),
    "engagement_fallback_value": (0.0, 1.0),
    "hot_gravity": (0.001, 0.5),  # FR-023
    "hot_clicks_weight": (0.0, 5.0),  # FR-023
    "hot_impressions_weight": (0.0, 5.0),  # FR-023
    "w_cooccurrence": (0.0, 1.0),  # FR-025
    "co_occurrence_fallback_value": (0.0, 1.0),  # FR-025
}
_VALUE_MODEL_INT_BOUNDS: dict[str, tuple[int, int]] = {
    "traffic_lookback_days": (1, 365),
    "engagement_lookback_days": (1, 365),
    "engagement_words_per_minute": (50, 600),
    "hot_lookback_days": (7, 365),  # FR-023
    "co_occurrence_min_co_sessions": (1, 100),  # FR-025
}
_VALUE_MODEL_BOOL_KEYS: tuple[str, ...] = (
    "enabled",
    "engagement_signal_enabled",
    "hot_decay_enabled",  # FR-023
    "co_occurrence_signal_enabled",  # FR-025
)


def _validate_value_model_settings(payload: dict, current: dict) -> dict:
    """Validate value-model settings with the lenient "clamp don't reject" contract.

    Bad operator input is silently clamped to the nearest valid value instead
    of raising — matches spec FR-013 / FR-023 / FR-025 expectations.
    """
    validated: dict = {
        key: coerce_lenient_bool(payload, current, key)
        for key in _VALUE_MODEL_BOOL_KEYS
    }
    for key, (lo, hi) in _VALUE_MODEL_FLOAT_BOUNDS.items():
        validated[key] = coerce_clamp_float(payload, current, key, lo, hi)
    for key, (lo_i, hi_i) in _VALUE_MODEL_INT_BOUNDS.items():
        validated[key] = coerce_clamp_int(payload, current, key, lo_i, hi_i)
    return validated


class ValueModelSettingsView(APIView):
    """
    GET  /api/settings/value-model/ - returns FR-021 value model settings
    PUT  /api/settings/value-model/ - validates and persists those settings
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.settings_helpers import get_value_model_settings

        return Response(get_value_model_settings())

    def put(self, request):
        """Persist a validated value-model settings payload.

        Refactored 2026-05-04: was a 143-line monolith mostly composed
        of a giant ``rows`` dict literal. Extracted that into the pure
        helper ``_build_value_model_rows`` so the handler stays under
        the lint budget AND the row-shape is independently testable.
        """
        from apps.core.models import AppSetting
        from apps.core.services.settings_helpers import get_value_model_settings

        current = get_value_model_settings()
        try:
            validated = _validate_value_model_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)

        for key, row in _build_value_model_rows(validated).items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "ml",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


# ── Spam-guard defaults, accessor, validator, row builder, view ──


DEFAULT_SPAM_GUARD_SETTINGS: dict[str, int] = {
    "max_existing_links_per_host": 2,
    "max_anchor_words": 4,
    "paragraph_window": 3,
}


_SPAM_GUARD_KEYS = (
    "max_existing_links_per_host",
    "max_anchor_words",
    "paragraph_window",
)


def get_spam_guard_settings() -> dict[str, int]:
    """Return current spam-guard limits, falling back to patent-backed defaults."""
    return {
        key: read_app_setting_int(
            f"spam_guards.{key}",
            DEFAULT_SPAM_GUARD_SETTINGS[key],
        )
        for key in _SPAM_GUARD_KEYS
    }


def _validate_spam_guard_settings(payload: dict, current: dict) -> dict[str, int]:
    """Validate and clamp spam-guard settings."""

    def _get_int(key: str, lo: int, hi: int) -> int:
        val = payload.get(key, current.get(key))
        try:
            return max(lo, min(hi, int(val)))
        except (TypeError, ValueError):
            return current.get(key, DEFAULT_SPAM_GUARD_SETTINGS[key])

    return {
        "max_existing_links_per_host": _get_int("max_existing_links_per_host", 1, 20),
        "max_anchor_words": _get_int("max_anchor_words", 1, 10),
        "paragraph_window": _get_int("paragraph_window", 1, 10),
    }


# Spam-guard row spec. Descriptions cite the specific patent / source so the
# operator-visible AppSetting row carries provenance.
_SPAM_GUARD_ROW_SPEC: tuple[tuple[str, str, str, str], ...] = (
    (
        "max_existing_links_per_host",
        "spam_guards.max_existing_links_per_host",
        "int",
        "Maximum number of existing outgoing body links a host page may "
        "already carry before the pipeline skips it. "
        "Default 3 — Ntoulas et al. anchor-word fraction research (US20060184500A1).",
    ),
    (
        "max_anchor_words",
        "spam_guards.max_anchor_words",
        "int",
        "Maximum number of words allowed in a suggested anchor phrase. "
        "Default 4 — Google recommends 2–5 words; US8380722B2 confirms "
        "anchors are 'usually short and descriptive'.",
    ),
    (
        "paragraph_window",
        "spam_guards.paragraph_window",
        "int",
        "Sentence-position window for paragraph-cluster detection. "
        "Two suggestions within this many sentences of each other on "
        "the same host are treated as the same paragraph — only the "
        "higher-scoring one is kept. Default 3 — US8577893B1.",
    ),
)


def _build_spam_guard_rows(validated: dict) -> dict[str, dict]:
    """Pure function — turn a validated spam-guard dict into AppSetting rows."""
    return {
        setting_key: {
            "value": _format_setting_value(validated[validated_key], value_type),
            "value_type": value_type,
            "description": description,
        }
        for validated_key, setting_key, value_type, description in _SPAM_GUARD_ROW_SPEC
    }


class SpamGuardSettingsView(APIView):
    """
    GET  /api/settings/spam-guards/  — returns current spam-guard limits
    PUT  /api/settings/spam-guards/  — validates and persists new limits

    Controls three pipeline guards that prevent the tool from producing
    spammy internal-link suggestions (backed by Ntoulas et al., US8380722B2,
    US8577893B1, and the 2024 Google API leak findings):

    * max_existing_links_per_host — skip a host page if it already has this
      many outgoing body links (default 3).
    * max_anchor_words — reject anchor text longer than this many words
      (default 4, matching Google's 2–5 word recommendation).
    * paragraph_window — block a second suggestion within this many sentence
      positions of an already-selected one on the same host (default 3).
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(get_spam_guard_settings())

    def put(self, request):
        from apps.core.models import AppSetting

        current = get_spam_guard_settings()
        try:
            validated = _validate_spam_guard_settings(request.data, current)
        except ValueError as exc:
            return Response({"error": str(exc)}, status=400)
        for key, row in _build_spam_guard_rows(validated).items():
            AppSetting.objects.update_or_create(
                key=key,
                defaults={
                    "value": row["value"],
                    "value_type": row["value_type"],
                    "category": "anchor",
                    "description": row["description"],
                    "is_secret": False,
                },
            )
        return Response(validated)


class GraphRebuildView(APIView):
    """POST /api/settings/graph/rebuild/ - manual trigger for bipartite graph refresh."""

    permission_classes = [IsAuthenticated]
    throttle_classes = [_GraphRebuildThrottle]

    def post(self, request):
        from apps.pipeline.tasks import dispatch_graph_rebuild

        job_id = str(uuid.uuid4())
        payload = dispatch_graph_rebuild(job_id=job_id)
        return Response(payload, status=202)


# ── User / auth views ────────────────────────────────────────────


class UserMeView(APIView):
    """
    Returns the currently authenticated user's profile.
    Returns 401 when no valid token is provided.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(
            {
                "id": request.user.id,
                "username": request.user.username,
                "email": request.user.email,
                "is_staff": request.user.is_staff,
                "date_joined": request.user.date_joined,
            }
        )


class UserLogoutView(APIView):
    """
    Deletes the user's auth token, invalidating all future requests with it.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            request.user.auth_token.delete()
        except Exception:
            logger.debug("Auth token delete failed or already gone", exc_info=True)
        return Response({"status": "success"})


class LocalVerificationBootstrapView(APIView):
    """Mint a localhost-only auth token for browser verification.

    Three independent gates must all pass before a token is issued:
    1. LOCAL_VERIFICATION_BOOTSTRAP_ENABLED must be True (opt-in, default False).
    2. The request must carry the X-XFIL-Verification: playwright header.
    3. The TCP peer IP (REMOTE_ADDR) must be the loopback address — this
       cannot be spoofed via HTTP headers the way the Host header can.

    The endpoint ONLY ever creates or repairs the 'playwright-local' throwaway
    account. It never touches any other user's credentials or returns any other
    user's token, regardless of what accounts exist in the database.
    """

    authentication_classes = []
    permission_classes = []
    VERIFICATION_HEADER = "HTTP_X_XFIL_VERIFICATION"
    _PLAYWRIGHT_USERNAME = "playwright-local"
    _PLAYWRIGHT_EMAIL = "playwright-local@example.invalid"

    def post(self, request):
        if not self._request_is_authorised(request):
            return Response({"detail": "Not found."}, status=404)

        from rest_framework.authtoken.models import Token

        user = self._get_or_repair_playwright_user()
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username})

    def _request_is_authorised(self, request) -> bool:
        """Three-gate guard: feature flag, secret header, and loopback peer IP."""
        if not getattr(django_settings, "LOCAL_VERIFICATION_BOOTSTRAP_ENABLED", False):
            return False
        if request.META.get(self.VERIFICATION_HEADER) != "playwright":
            return False
        # Use the TCP peer IP, not the Host header (which is attacker-controlled).
        peer_ip = request.META.get("REMOTE_ADDR", "")
        return peer_ip in {"127.0.0.1", "::1"}

    def _get_or_repair_playwright_user(self):
        """Get-or-create + heal the playwright-local account.

        Repairs stale playwright-local accounts unconditionally (not only on
        first creation) so a previously-downgraded account is always healed.
        Touches the playwright-local account and only the playwright-local
        account — protected by ABSOLUTE rule "Never change user passwords".
        """
        from django.contrib.auth import get_user_model

        user_model = get_user_model()
        user, _ = user_model.objects.get_or_create(
            username=self._PLAYWRIGHT_USERNAME,
            defaults={
                "email": self._PLAYWRIGHT_EMAIL,
                "is_staff": True,
                "is_superuser": True,
            },
        )
        fields_to_update: list[str] = []
        if not user.is_staff:
            user.is_staff = True
            fields_to_update.append("is_staff")
        if not user.is_superuser:
            user.is_superuser = True
            fields_to_update.append("is_superuser")
        if user.email != self._PLAYWRIGHT_EMAIL:
            user.email = self._PLAYWRIGHT_EMAIL
            fields_to_update.append("email")
        if user.has_usable_password():
            # Playwright uses token auth; a usable password is a liability.
            user.set_unusable_password()
            fields_to_update.append("password")
        if fields_to_update:
            user.save(update_fields=fields_to_update)
        return user


def _client_is_local_setup_request(request) -> bool:
    """Return True only for localhost or the local Docker proxy path."""
    peer_ip = request.META.get("REMOTE_ADDR", "")
    forwarded_for = (
        (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")[0].strip()
    )
    if peer_ip in {"127.0.0.1", "::1"}:
        return True
    return peer_ip.startswith("172.") and forwarded_for in {"127.0.0.1", "::1"}


class FirstOperatorSetupView(APIView):
    """Create the first local operator account when the user table is empty."""

    authentication_classes = []
    permission_classes = []

    def get(self, request):
        from django.contrib.auth import get_user_model

        available = (
            _client_is_local_setup_request(request)
            and not get_user_model().objects.exists()
        )
        return Response({"available": available, "username": "admin"})

    def post(self, request):
        from django.contrib.auth import get_user_model
        from django.contrib.auth.password_validation import validate_password
        from django.core.exceptions import ValidationError
        from rest_framework.authtoken.models import Token

        if not _client_is_local_setup_request(request):
            return Response({"detail": "Not found."}, status=404)

        user_model = get_user_model()
        if user_model.objects.exists():
            return Response(
                {"detail": "First operator setup is already closed."},
                status=404,
            )

        username = str(request.data.get("username") or "").strip()
        password = str(request.data.get("password") or "")
        email = str(request.data.get("email") or "admin@example.com").strip()
        if username != "admin":
            return Response(
                {"detail": "The first operator username must be admin."},
                status=400,
            )
        if not password:
            return Response({"detail": "Password is required."}, status=400)
        try:
            validate_password(password)
        except ValidationError as exc:
            return Response({"detail": " ".join(exc.messages)}, status=400)

        user = user_model.objects.create_superuser(
            username=username,
            email=email,
            password=password,
        )
        token, _ = Token.objects.get_or_create(user=user)
        return Response({"token": token.key, "username": user.username})


# ── Analytics / system-monitoring views ──────────────────────────


class ActiveUsersView(APIView):
    """GET /api/auth/active-users/ — who has made an authenticated request recently.

    Read by the dashboard's "whos on shift" widget. A user is considered
    active if their last_seen_at is within ``ACTIVE_WINDOW_MIN`` minutes.
    The caller is never omitted from the list — the frontend decides
    whether to hide the widget when the only active user is "me".
    """

    permission_classes = [IsAuthenticated]

    ACTIVE_WINDOW_MIN = 5

    def get(self, request):
        from datetime import timedelta

        from django.utils import timezone

        from .models import UserActivity

        cutoff = timezone.now() - timedelta(minutes=self.ACTIVE_WINDOW_MIN)
        rows = (
            UserActivity.objects.filter(last_seen_at__gte=cutoff)
            .select_related("user")
            .order_by("-last_seen_at")
        )
        payload = [
            {
                "username": r.user.username,
                "last_seen": r.last_seen_at.isoformat(),
                "route": r.last_route,
            }
            for r in rows
        ]
        return Response(payload)


# ── Phase 4.9 — Helper PC roster endpoint ─────────────────────────


class BudgetForecastView(APIView):
    """GET /api/system/budget-forecast/?task=<task_name>&kwarg1=value...

    Phase 4.2 — Budget & Space Forecasts pre-flight estimator.

    Returns an operator-facing forecast: estimated bytes, projected
    free-disk after the job, traffic-light verdict (safe / yellow / red),
    plain-English why, and the calibration history used.

    Query params:
        ?task=<task_name>      — required; must be a registered estimator
                                 (see GET /api/system/budget-forecast/tasks/
                                 for the full list)
        ?safety_margin_pct=N   — optional; overrides the 20% default
        ?<kwarg>=<value>       — every other query param is passed to the
                                 estimator function as a string-typed kwarg
                                 (the estimator coerces with int())
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.budget_forecaster import (
            forecast,
            get_registered_tasks,
        )

        task_name = request.query_params.get("task", "")
        if not task_name:
            return Response(
                {
                    "detail": "?task=<task_name> is required",
                    "available_tasks": get_registered_tasks(),
                },
                status=400,
            )

        kwargs: dict = {}
        for k, v in request.query_params.items():
            if k in {"task", "safety_margin_pct"}:
                continue
            kwargs[k] = v

        # Refactor 2026-05-04: shared coerce_int helper. Bad
        # `?safety_margin_pct=foo` falls back to None (= use the
        # forecaster's default 20% headroom) instead of being silently
        # dropped or crashing.
        margin = (
            coerce_int(
                request.query_params.get("safety_margin_pct"),
                default=-1,
                min_value=0,
                max_value=200,
            )
            if request.query_params.get("safety_margin_pct")
            else None
        )
        if margin is not None and margin < 0:
            margin = None

        result = forecast(
            task_name=task_name,
            kwargs=kwargs,
            safety_margin_pct=margin,
        )
        return Response(asdict(result))


class CachePolicySummaryView(APIView):
    """GET /api/system/cache-policy/

    Phase 4.13 — operator-facing cache stats. Returns one summary per
    cache layer with hit/miss/evict counts, hit ratio, estimated size,
    max-size budget, pin-count, and the list of pinned keys.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.cache_policy import summarise_all_layers

        return Response(
            {
                "layers": [asdict(s) for s in summarise_all_layers()],
            }
        )


class CompressionAuditView(APIView):
    """GET /api/system/compression-audit/

    Phase 4.9 — read-only view of the latest compression audit report.

    Returns the top-N tables where compression would save meaningful
    disk, plus the timestamp of the last audit run. The audit itself
    is a Celery beat task (``core.compression_audit``) that runs
    weekly; this endpoint is the operator-facing read.

    Response shape::

        {
            "run_at_iso": "2026-05-04T03:00:11+00:00",  // empty if never run
            "sample_size": 1000,
            "candidates": [...],
            "total_estimated_savings_bytes": 524288000,
            "total_estimated_savings_mb": 500,
            "note": "Audited 10 candidate tables; 7 have ≥1 MB projected savings."
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.compression_audit import get_last_compression_audit

        report = get_last_compression_audit()
        if report is None:
            return Response(
                {
                    "run_at_iso": "",
                    "sample_size": 0,
                    "candidates": [],
                    "total_estimated_savings_bytes": 0,
                    "total_estimated_savings_mb": 0,
                    "note": (
                        "No compression audit has run yet. The first audit "
                        "fires Sundays at 03:00 UTC; trigger immediately via "
                        "POST /api/system/compression-audit/run/."
                    ),
                }
            )
        payload = asdict(report)
        # Convert tuples → lists for JSON serialisation
        for c in payload["candidates"]:
            c["columns"] = list(c["columns"])
        payload["total_estimated_savings_mb"] = int(
            report.total_estimated_savings_bytes // (1024 * 1024)
        )
        return Response(payload)


class CompressionAuditRunView(APIView):
    """POST /api/system/compression-audit/run/

    Phase 4.9 — operator-triggered immediate audit. Useful when the
    operator just freed disk + wants to confirm the candidate list
    instead of waiting until Sunday's beat tick.

    Returns the freshly-computed report. Synchronous — typically takes
    30-120 seconds depending on corpus size. Restricted to staff users
    + rate-limited at 3/hour per user (``CompressionAuditRunThrottle``)
    so an accidentally-mashed button (or compromised non-admin token)
    can't pin the request-worker pool.
    """

    permission_classes = [IsAdminUser]
    throttle_classes = [CompressionAuditRunThrottle]

    def post(self, request):
        from dataclasses import asdict

        from apps.core.services.compression_audit import run_compression_audit

        report = run_compression_audit()
        payload = asdict(report)
        for c in payload["candidates"]:
            c["columns"] = list(c["columns"])
        payload["total_estimated_savings_mb"] = int(
            report.total_estimated_savings_bytes // (1024 * 1024)
        )
        return Response(payload)


class PerformanceCertView(APIView):
    """GET /api/system/performance-cert/

    Phase 4.11 — read-only "Ready to Ship?" badge. Returns the
    persisted pass/fail verdict computed by the Celery beat (daily) or
    by an operator-triggered run-now (POST run/ below).

    Response shape::

        {
            "run_at_iso": "2026-05-04T04:00:11+00:00",
            "verdict": "pass" | "warn" | "fail" | "unknown",
            "label": "Ready to ship — every benchmark meets baseline.",
            "benchmark_run_id": 42,
            "benchmark_run_started_at_iso": "2026-05-03T04:00:00+00:00",
            "areas": [
                {"area": "cpp", "fast_count": 8, "ok_count": 4,
                 "slow_count": 0, "total": 12, "verdict": "pass",
                 "note": "All 12 cpp benchmarks meet baseline."},
                ...
            ],
            "note": "All systems go..."
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.performance_certification import (
            get_last_certification,
        )

        verdict = get_last_certification()
        if verdict is None:
            return Response(
                {
                    "run_at_iso": "",
                    "verdict": "unknown",
                    "label": (
                        "No performance certification has run yet. The first "
                        "cert fires daily at 04:00 UTC; trigger immediately "
                        "via POST /api/system/performance-cert/run/."
                    ),
                    "benchmark_run_id": None,
                    "benchmark_run_started_at_iso": "",
                    "areas": [],
                    "note": "",
                }
            )
        return Response(asdict(verdict))


class PerformanceCertRunView(APIView):
    """POST /api/system/performance-cert/run/

    Phase 4.11 — operator-triggered immediate cert recompute. Cheap
    (~1-2 s) — aggregates the latest BenchmarkRun without re-running
    benchmarks. Restricted to staff users + 6/hour throttle so an
    accidentally-mashed button can't pile up audit-event noise.

    To trigger a FRESH benchmark run (5-15 minutes) use
    ``POST /api/benchmarks/trigger/``; this endpoint only re-aggregates
    the latest existing run.
    """

    permission_classes = [IsAdminUser]
    throttle_classes = [PerformanceCertRunThrottle]

    def post(self, request):
        from dataclasses import asdict

        from apps.core.services.performance_certification import (
            run_performance_certification,
        )

        verdict = run_performance_certification()
        return Response(asdict(verdict))


class CppFallbackStatusView(APIView):
    """GET /api/system/cpp-fallback/

    Phase 4.14 — C++ Fallback Warning summary. Returns the live
    runtime-path status of every C++ extension plus a one-line banner
    message the dashboard can render at the top of the page when ANY
    extension is on the Python fallback.

    Response shape::

        {
            "total_extensions": 17,
            "on_cpp": 16,
            "on_python_fallback": 1,
            "banner": "Performance warning: …",  // empty when all loaded
            "fallbacks": [
                {
                    "module": "ivf_index",
                    "label": "IVF index search",
                    "critical": true,
                    "fallback_reason": "ABI mismatch: …",
                    "since_iso": "2026-05-04T17:32:11+00:00",
                    "duration_seconds": 7321
                }
            ]
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.services.cpp_fallback_warning import (
            format_dashboard_banner,
            get_current_fallback_status,
        )

        snap = get_current_fallback_status()
        payload = asdict(snap)
        payload["banner"] = format_dashboard_banner()
        return Response(payload)


class CachePolicyPinView(APIView):
    """POST /api/system/cache-policy/<layer>/pin/   {"key": "<cache_key>"}
    DELETE /api/system/cache-policy/<layer>/pin/   {"key": "<cache_key>"}

    Phase 4.13 — pin / unpin a cache key so the eviction policy keeps
    or releases it. Pin-set lives in AppSetting (one row per pin).
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, layer: str):
        from apps.core.services.cache_policy import pin_key

        key = (request.data.get("key") or "").strip()
        if not key:
            return Response({"detail": "Body must include 'key'."}, status=400)
        pin_key(layer, key)
        return Response({"layer": layer, "key": key, "pinned": True})

    def delete(self, request, layer: str):
        from apps.core.services.cache_policy import unpin_key

        key = (request.data.get("key") or "").strip()
        if not key:
            return Response({"detail": "Body must include 'key'."}, status=400)
        unpin_key(layer, key)
        return Response({"layer": layer, "key": key, "pinned": False})


class CachePolicyEvictView(APIView):
    """POST /api/system/cache-policy/<layer>/evict/   {"key": "<key>"} (optional)

    Phase 4.13 — operator-triggered cache purge. With ``key`` set the
    single entry is removed; without ``key`` the whole layer is
    purged (pinned keys are skipped). Returns the lists of
    ``removed_keys`` and ``skipped_pinned`` for the UI snackbar.
    """

    permission_classes = [IsAuthenticated]

    def post(self, request, layer: str):
        from apps.core.services.cache_policy import evict_on_demand

        key = (request.data.get("key") or "").strip() or None
        result = evict_on_demand(layer, key=key)
        return Response({"layer": layer, **result})


class BudgetForecastTasksView(APIView):
    """GET /api/system/budget-forecast/tasks/

    Lists the task_names the budget forecaster knows about. Used by the
    pre-flight chip's task picker.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.services.budget_forecaster import get_registered_tasks

        return Response({"tasks": get_registered_tasks()})


class HelpersRosterView(APIView):
    """GET /api/helpers/

    Returns the right-now state of every connected helper PC, shaped
    for the frontend roster card + Confidence Meter contributor.
    Cached 60 s in Redis via the ``roster()`` helper. Empty list when
    no helpers are connected (the operator hasn't enrolled any yet) —
    callers should treat empty as "main PC handles everything",
    not as an error.

    Response shape::

        {
            "online_count": 1,
            "accepting_work_count": 1,
            "sampled_at": "2026-05-02T12:34:56+00:00",
            "helpers": [
                {
                    "name": "helper-cpu-1",
                    "role": "worker",
                    "status": "online",
                    "accepting_work": true,
                    "heartbeat_age_seconds": 12,
                    "has_gpu": false,
                    "cpu_pct": 22.4,
                    "ram_pct": 41.0,
                    "active_jobs": 1,
                    "queued_jobs": 0,
                    "allowed_queues": ["cpu_only", "default"],
                    "allowed_job_types": ["enrichment", "audience"],
                    "warmed_model_keys": [],
                    "capabilities": {"cpu_cores": 8, "ram_gb": 16, "gpu_vram_gb": 0}
                }
            ]
        }
    """

    permission_classes = [IsAuthenticated]

    def get(self, request):
        from dataclasses import asdict

        from apps.core.helpers import roster

        snap = roster()
        return Response(
            {
                "online_count": snap.online_count,
                "accepting_work_count": snap.accepting_work_count,
                "sampled_at": snap.sampled_at,
                "helpers": [asdict(h) for h in snap.helpers],
            }
        )
