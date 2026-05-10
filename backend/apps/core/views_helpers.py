"""
Helper node management and heartbeat views extracted from ``views_capacity.py``.
Part of the domain-driven decomposition to stay under the 1500-line cap.
"""

from __future__ import annotations

import hashlib
import logging

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.api.query_params import coerce_bool, coerce_float, coerce_int

logger = logging.getLogger(__name__)


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


# ── Heartbeat helpers ─────────────────────────────────────────────


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
    """Apply non-numeric identity fields."""
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
    """Apply CPU + queue-depth metrics."""
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
    """Apply GPU utilisation + VRAM metrics."""
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
    """POST /api/settings/helpers/<id>/heartbeat/"""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
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


class HelpersRosterView(APIView):
    """GET /api/helpers/ — state of every connected helper PC."""

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
