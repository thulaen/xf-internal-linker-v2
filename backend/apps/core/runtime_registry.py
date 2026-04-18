"""Shared runtime-registry helpers.

This module provides one source of truth for model/runtime summaries used by
Mission Critical, System Health, Settings, and runtime actions.
"""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from typing import Any

from django.conf import settings as django_settings
from django.db.models import Max
from django.utils import timezone

from apps.core.models import AppSetting, HelperNode
from apps.core.runtime_models import (
    HardwareCapabilitySnapshot,
    RuntimeAuditLog,
    RuntimeModelBackfillPlan,
    RuntimeModelPlacement,
    RuntimeModelRegistry,
)


ACTIVE_HELPER_STATUSES = {"online", "busy", "stale"}
MODEL_TASK_EMBEDDING = "embedding"


@dataclass(frozen=True)
class RuntimeProfileRecommendation:
    profile: str
    reason: str
    suggested_batch_size: int
    suggested_concurrency: int


def get_current_embedding_model_name() -> str:
    setting = AppSetting.objects.filter(key="embedding_model").first()
    if setting and setting.value.strip():
        return setting.value.strip()
    return getattr(django_settings, "EMBEDDING_MODEL", "BAAI/bge-m3")


def get_current_embedding_device() -> str:
    try:
        import torch

        return "cuda" if torch.cuda.is_available() else "cpu"
    except Exception:
        return "cpu"


def get_active_runtime_model(
    task_type: str = MODEL_TASK_EMBEDDING,
) -> RuntimeModelRegistry | None:
    champion = (
        RuntimeModelRegistry.objects.filter(task_type=task_type, role="champion")
        .exclude(status="deleted")
        .order_by("-promoted_at", "-updated_at")
        .first()
    )
    if champion:
        return champion

    model_name = get_current_embedding_model_name()
    registry, _ = RuntimeModelRegistry.objects.get_or_create(
        task_type=task_type,
        model_name=model_name,
        algorithm_version="fr020-v1",
        defaults={
            "model_family": "sentence-transformers",
            "dimension": 1024 if task_type == MODEL_TASK_EMBEDDING else None,
            "device_target": get_current_embedding_device(),
            "batch_size": int(
                AppSetting.objects.filter(key="system.embedding_batch_size")
                .values_list("value", flat=True)
                .first()
                or 32
            ),
            "role": "champion",
            "status": "ready",
            "health_result": {"state": "inferred"},
            "algorithm_version": "fr020-v1",
        },
    )
    if registry.role != "champion" or registry.status == "deleted":
        registry.role = "champion"
        registry.status = "ready"
        registry.save(update_fields=["role", "status", "updated_at"])
    return registry


def get_candidate_runtime_model(
    task_type: str = MODEL_TASK_EMBEDDING,
) -> RuntimeModelRegistry | None:
    return (
        RuntimeModelRegistry.objects.filter(task_type=task_type, role="candidate")
        .exclude(status="deleted")
        .order_by("-updated_at")
        .first()
    )


def record_runtime_audit(
    *,
    action: str,
    subject_type: str,
    message: str,
    subject_id: str = "",
    actor: str = "",
    metadata: dict[str, Any] | None = None,
) -> None:
    RuntimeAuditLog.objects.create(
        action=action,
        subject_type=subject_type,
        subject_id=subject_id,
        actor=actor,
        message=message,
        metadata=metadata or {},
    )
    retained_ids = list(
        RuntimeAuditLog.objects.order_by("-created_at").values_list("id", flat=True)[
            :1000
        ]
    )
    RuntimeAuditLog.objects.exclude(id__in=retained_ids).delete()


def summarize_model_registry(task_type: str = MODEL_TASK_EMBEDDING) -> dict[str, Any]:
    champion = get_active_runtime_model(task_type)
    candidate = get_candidate_runtime_model(task_type)
    latest_backfill = (
        RuntimeModelBackfillPlan.objects.select_related("from_model", "to_model")
        .order_by("-created_at")
        .first()
    )
    placements = RuntimeModelPlacement.objects.select_related(
        "registry", "helper"
    ).filter(registry__task_type=task_type)

    placement_rows = []
    reclaimable_bytes = 0
    for placement in placements.order_by(
        "registry__role", "executor_type", "helper__name"
    ):
        placement_rows.append(
            {
                "id": placement.id,
                "registry_id": placement.registry_id,
                "model_name": placement.registry.model_name,
                "role": placement.registry.role,
                "executor_type": placement.executor_type,
                "helper_id": placement.helper_id,
                "helper_name": placement.helper.name if placement.helper_id else "",
                "artifact_path": placement.artifact_path,
                "disk_bytes": placement.disk_bytes,
                "status": placement.status,
                "last_used_at": placement.last_used_at.isoformat()
                if placement.last_used_at
                else None,
                "warmed_at": placement.warmed_at.isoformat()
                if placement.warmed_at
                else None,
                "last_error": placement.last_error,
                "deletable": placement.registry.role == "retired"
                and placement.status not in {"warming", "draining", "deleted"},
            }
        )
        if placement.registry.role == "retired" and placement.status != "deleted":
            reclaimable_bytes += int(placement.disk_bytes or 0)

    return {
        "task_type": task_type,
        "active_model": _serialize_model(champion),
        "candidate_model": _serialize_model(candidate),
        "placements": placement_rows,
        "reclaimable_disk_bytes": reclaimable_bytes,
        "backfill": _serialize_backfill(latest_backfill),
        "device": get_current_embedding_device(),
        "hot_swap_safe": candidate is None or candidate.status == "ready",
        "recent_audit_log": [
            {
                "id": entry.id,
                "created_at": entry.created_at.isoformat(),
                "action": entry.action,
                "subject_type": entry.subject_type,
                "subject_id": entry.subject_id,
                "actor": entry.actor,
                "message": entry.message,
                "metadata": entry.metadata,
            }
            for entry in RuntimeAuditLog.objects.order_by("-created_at")[:10]
        ],
        "last_audit_at": RuntimeAuditLog.objects.aggregate(m=Max("created_at"))[
            "m"
        ].isoformat()
        if RuntimeAuditLog.objects.exists()
        else None,
    }


def summarize_helpers() -> dict[str, Any]:
    now = timezone.now()
    online = 0
    busy = 0
    stale = 0
    offline = 0
    aggregate_ram_pressure = 0.0
    busiest_name = ""
    busiest_load = 0.0
    nodes = list(HelperNode.objects.all().order_by("name"))

    for node in nodes:
        state = helper_state(node, now=now)
        if state == "online":
            online += 1
        elif state == "busy":
            busy += 1
        elif state == "stale":
            stale += 1
        else:
            offline += 1

        aggregate_ram_pressure += min(
            1.0, max(0.0, float(node.ram_pct or 0.0) / max(node.ram_cap_pct or 1, 1))
        )
        load = helper_effective_load(node)
        if load >= busiest_load:
            busiest_load = load
            busiest_name = node.name

    avg_ram_pressure = aggregate_ram_pressure / len(nodes) if nodes else 0.0
    return {
        "counts": {
            "online": online,
            "busy": busy,
            "stale": stale,
            "offline": offline,
        },
        "busiest": {
            "name": busiest_name,
            "effective_load": round(busiest_load, 4),
        },
        "aggregate_ram_pressure": round(avg_ram_pressure, 4),
        "helpers_enabled": bool(nodes),
    }


def helper_state(node: HelperNode, *, now=None) -> str:
    if now is None:
        now = timezone.now()
    if node.status == "offline" or node.last_heartbeat is None:
        return "offline"
    age_seconds = (now - node.last_heartbeat).total_seconds()
    if age_seconds > 300:
        return "offline"
    if age_seconds > 120:
        return "stale"
    if node.status == "busy" or (node.active_jobs or 0) > 0:
        return "busy"
    return "online"


def helper_effective_load(node: HelperNode) -> float:
    slot_pressure = float(node.active_jobs or 0) / max(
        int(node.max_concurrency or 1), 1
    )
    cpu_pressure = float(node.cpu_pct or 0.0) / max(float(node.cpu_cap_pct or 1), 1.0)
    ram_pressure = float(node.ram_pct or 0.0) / max(float(node.ram_cap_pct or 1), 1.0)
    gpu_pressure = 0.0
    if node.gpu_util_pct is not None:
        gpu_pressure = max(gpu_pressure, float(node.gpu_util_pct or 0.0) / 100.0)
    if node.gpu_vram_used_mb and node.gpu_vram_total_mb:
        gpu_pressure = max(
            gpu_pressure,
            float(node.gpu_vram_used_mb) / max(float(node.gpu_vram_total_mb), 1.0),
        )
    return min(1.0, max(slot_pressure, cpu_pressure, ram_pressure, gpu_pressure))


def capture_primary_hardware_snapshot(
    *, force: bool = False
) -> HardwareCapabilitySnapshot:
    import shutil

    previous = (
        HardwareCapabilitySnapshot.objects.filter(node_kind="primary")
        .order_by("-created_at")
        .first()
    )
    if (
        not force
        and previous is not None
        and (timezone.now() - previous.created_at).total_seconds() < 3600
    ):
        return previous

    cpu_cores = os.cpu_count() or 0
    ram_gb = 0.0
    gpu_name = ""
    gpu_vram_gb = 0.0
    native_kernels_healthy = False
    disk_free_gb = 0.0
    snapshot: dict[str, Any] = {"cpu_cores": cpu_cores}

    try:
        import psutil

        ram_gb = round(psutil.virtual_memory().total / (1024**3), 2)
        snapshot["ram_gb"] = ram_gb
    except Exception:
        pass

    try:
        usage = shutil.disk_usage("/app" if os.name != "nt" else os.getcwd())
        disk_free_gb = round(usage.free / (1024**3), 2)
        snapshot["disk_free_gb"] = disk_free_gb
    except Exception:
        pass

    try:
        import torch

        if torch.cuda.is_available():
            props = torch.cuda.get_device_properties(0)
            gpu_name = props.name
            gpu_vram_gb = round(props.total_memory / (1024**3), 2)
            snapshot["gpu_name"] = gpu_name
            snapshot["gpu_vram_gb"] = gpu_vram_gb
    except Exception:
        pass

    try:
        from apps.diagnostics.health import _native_module_runtime_status

        native_kernels_healthy = all(
            status["state"] == "healthy" or not status["critical"]
            for status in _native_module_runtime_status()
        )
    except Exception:
        native_kernels_healthy = False

    detected_upgrade = False
    if previous:
        detected_upgrade = bool(
            cpu_cores > previous.cpu_cores
            or ram_gb > previous.ram_gb
            or gpu_vram_gb > previous.gpu_vram_gb
        )

    snapshot_row = HardwareCapabilitySnapshot.objects.create(
        node_kind="primary",
        cpu_cores=cpu_cores,
        ram_gb=ram_gb,
        gpu_name=gpu_name,
        gpu_vram_gb=gpu_vram_gb,
        disk_free_gb=disk_free_gb,
        native_kernels_healthy=native_kernels_healthy,
        snapshot=snapshot,
        detected_upgrade=detected_upgrade,
    )
    retained_ids = list(
        HardwareCapabilitySnapshot.objects.filter(node_kind="primary")
        .order_by("-created_at")
        .values_list("id", flat=True)[:50]
    )
    HardwareCapabilitySnapshot.objects.filter(node_kind="primary").exclude(
        id__in=retained_ids
    ).delete()
    return snapshot_row


def get_latest_primary_hardware_snapshot() -> HardwareCapabilitySnapshot:
    snapshot = (
        HardwareCapabilitySnapshot.objects.filter(node_kind="primary")
        .order_by("-created_at")
        .first()
    )
    if snapshot:
        return snapshot
    return capture_primary_hardware_snapshot()


def recommend_runtime_profile(
    snapshot: HardwareCapabilitySnapshot | None = None,
) -> RuntimeProfileRecommendation:
    snapshot = snapshot or get_latest_primary_hardware_snapshot()
    if snapshot.gpu_vram_gb >= 10 or snapshot.ram_gb >= 32:
        return RuntimeProfileRecommendation(
            profile="high",
            reason="This machine has enough RAM or VRAM headroom to run larger batches safely.",
            suggested_batch_size=64,
            suggested_concurrency=4,
        )
    if snapshot.ram_gb >= 16:
        return RuntimeProfileRecommendation(
            profile="balanced",
            reason="This machine can handle the default BGE-M3 setup with safe headroom.",
            suggested_batch_size=32,
            suggested_concurrency=2,
        )
    return RuntimeProfileRecommendation(
        profile="safe",
        reason="This machine is memory-constrained, so the safe profile avoids noob-unfriendly stalls.",
        suggested_batch_size=16,
        suggested_concurrency=1,
    )


def runtime_summary_payload() -> dict[str, Any]:
    snapshot = get_latest_primary_hardware_snapshot()
    recommendation = recommend_runtime_profile(snapshot)
    return {
        "model_runtime": summarize_model_registry(),
        "helper_nodes": summarize_helpers(),
        "hardware": {
            "cpu_cores": snapshot.cpu_cores,
            "ram_gb": snapshot.ram_gb,
            "gpu_name": snapshot.gpu_name,
            "gpu_vram_gb": snapshot.gpu_vram_gb,
            "disk_free_gb": snapshot.disk_free_gb,
            "native_kernels_healthy": snapshot.native_kernels_healthy,
            "detected_upgrade": snapshot.detected_upgrade,
            "captured_at": snapshot.created_at.isoformat(),
        },
        "recommended_profile": asdict(recommendation),
    }


def _serialize_model(model: RuntimeModelRegistry | None) -> dict[str, Any] | None:
    if model is None:
        return None
    return {
        "id": model.id,
        "task_type": model.task_type,
        "model_name": model.model_name,
        "model_family": model.model_family,
        "dimension": model.dimension,
        "device_target": model.device_target,
        "batch_size": model.batch_size,
        "memory_profile": model.memory_profile,
        "role": model.role,
        "status": model.status,
        "health_result": model.health_result,
        "algorithm_version": model.algorithm_version,
        "promoted_at": model.promoted_at.isoformat() if model.promoted_at else None,
        "draining_since": model.draining_since.isoformat()
        if model.draining_since
        else None,
        "last_warmup_result": model.last_warmup_result,
    }


def _serialize_backfill(plan: RuntimeModelBackfillPlan | None) -> dict[str, Any] | None:
    if plan is None:
        return None
    return {
        "id": plan.id,
        "from_model_id": plan.from_model_id,
        "to_model_id": plan.to_model_id,
        "status": plan.status,
        "compatibility_status": plan.compatibility_status,
        "progress_pct": plan.progress_pct,
        "checkpoint": plan.checkpoint,
        "last_error": plan.last_error,
    }
