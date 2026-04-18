"""Runtime registry and helper/runtime summary endpoints."""

from __future__ import annotations

from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.models import AppSetting, HelperNode
from apps.core.runtime_models import (
    RuntimeModelBackfillPlan,
    RuntimeModelPlacement,
    RuntimeModelRegistry,
)
from apps.core.runtime_registry import (
    capture_primary_hardware_snapshot,
    get_active_runtime_model,
    helper_state,
    record_runtime_audit,
    runtime_summary_payload,
    summarize_model_registry,
)


def serialize_helper_node(node: HelperNode) -> dict[str, object]:
    return {
        "id": node.id,
        "name": node.name,
        "role": node.role,
        "status": node.status,
        "derived_state": helper_state(node),
        "capabilities": node.capabilities,
        "allowed_queues": node.allowed_queues,
        "allowed_job_types": node.allowed_job_types,
        "time_policy": node.time_policy,
        "max_concurrency": node.max_concurrency,
        "cpu_cap_pct": node.cpu_cap_pct,
        "ram_cap_pct": node.ram_cap_pct,
        "accepting_work": node.accepting_work,
        "active_jobs": node.active_jobs,
        "queued_jobs": node.queued_jobs,
        "cpu_pct": node.cpu_pct,
        "ram_pct": node.ram_pct,
        "gpu_util_pct": node.gpu_util_pct,
        "gpu_vram_used_mb": node.gpu_vram_used_mb,
        "gpu_vram_total_mb": node.gpu_vram_total_mb,
        "network_rtt_ms": node.network_rtt_ms,
        "native_kernels_healthy": node.native_kernels_healthy,
        "warmed_model_keys": node.warmed_model_keys,
        "last_heartbeat": node.last_heartbeat.isoformat()
        if node.last_heartbeat
        else None,
        "last_snapshot_at": node.last_snapshot_at.isoformat()
        if node.last_snapshot_at
        else None,
    }


class RuntimeModelsView(APIView):
    """GET/POST /api/settings/runtime/models/."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        task_type = (
            str(request.query_params.get("task_type") or "embedding").strip()
            or "embedding"
        )
        return Response(summarize_model_registry(task_type))

    def post(self, request):
        data = request.data or {}
        task_type = str(data.get("task_type") or "embedding").strip() or "embedding"
        model_name = str(data.get("model_name") or "").strip()
        if not model_name:
            return Response({"error": "model_name is required."}, status=400)

        registry, created = RuntimeModelRegistry.objects.get_or_create(
            task_type=task_type,
            model_name=model_name,
            algorithm_version=str(data.get("algorithm_version") or "fr020-v1"),
            defaults={
                "model_family": str(
                    data.get("model_family") or "sentence-transformers"
                ),
                "dimension": data.get("dimension"),
                "device_target": str(data.get("device_target") or "cpu"),
                "batch_size": int(data.get("batch_size") or 32),
                "memory_profile": data.get("memory_profile") or {},
                "role": str(data.get("role") or "candidate"),
                "status": "registered",
                "health_result": {},
            },
        )
        if not created:
            for field in ("model_family", "dimension", "device_target", "batch_size"):
                if field in data:
                    setattr(registry, field, data[field])
            if "memory_profile" in data:
                registry.memory_profile = data["memory_profile"] or {}
            if "role" in data:
                registry.role = str(data["role"] or registry.role)
            registry.save()

        executor_type = str(data.get("executor_type") or "primary")
        helper = None
        if executor_type == "helper" and data.get("helper_id"):
            helper = HelperNode.objects.filter(pk=data["helper_id"]).first()
            if helper is None:
                return Response({"error": "helper_id not found."}, status=404)
        placement, _ = RuntimeModelPlacement.objects.get_or_create(
            registry=registry,
            executor_type=executor_type,
            helper=helper,
            defaults={
                "artifact_path": str(data.get("artifact_path") or ""),
                "artifact_checksum": str(data.get("artifact_checksum") or ""),
                "disk_bytes": int(data.get("disk_bytes") or 0),
                "status": "registered",
            },
        )
        record_runtime_audit(
            action="model.register",
            subject_type="runtime_model",
            subject_id=str(registry.id),
            actor=getattr(request.user, "username", ""),
            message=f"Registered {registry.model_name} as a {registry.role}.",
            metadata={"executor_type": executor_type, "placement_id": placement.id},
        )
        return Response(
            summarize_model_registry(task_type), status=201 if created else 200
        )


class RuntimeModelActionView(APIView):
    """POST /api/settings/runtime/models/<id>/action/."""

    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        try:
            registry = RuntimeModelRegistry.objects.get(pk=pk)
        except RuntimeModelRegistry.DoesNotExist:
            return Response({"error": "Runtime model not found."}, status=404)

        action = str(request.data.get("action") or "").strip().lower()
        if action not in {
            "download",
            "warm",
            "pause",
            "resume",
            "promote",
            "rollback",
            "drain",
        }:
            return Response({"error": f"Unsupported action: {action}"}, status=400)

        placement = None
        placement_id = request.data.get("placement_id")
        if placement_id:
            placement = RuntimeModelPlacement.objects.filter(
                pk=placement_id, registry=registry
            ).first()
            if placement is None:
                return Response({"error": "placement_id not found."}, status=404)
        else:
            placement = registry.placements.order_by(
                "executor_type", "helper__name"
            ).first()

        actor = getattr(request.user, "username", "")
        now = timezone.now()

        if action == "download":
            if placement is None:
                placement = RuntimeModelPlacement.objects.create(
                    registry=registry,
                    executor_type="primary",
                    status="downloading",
                )
            else:
                placement.status = "downloading"
                placement.save(update_fields=["status", "updated_at"])
            registry.status = "downloading"
            registry.save(update_fields=["status", "updated_at"])
            record_runtime_audit(
                action="model.download",
                subject_type="runtime_model",
                subject_id=str(registry.id),
                actor=actor,
                message=f"Started download metadata for {registry.model_name}.",
            )
            return Response({"status": "downloading", "placement_id": placement.id})

        if action == "warm":
            registry.status = "ready"
            registry.health_result = {
                "state": "ready",
                "checked_at": now.isoformat(),
                "note": "Warmup metadata recorded. The model still loads lazily on first use.",
            }
            registry.last_warmup_result = dict(registry.health_result)
            registry.save(
                update_fields=[
                    "status",
                    "health_result",
                    "last_warmup_result",
                    "updated_at",
                ]
            )
            if placement is not None:
                placement.status = "ready"
                placement.warmed_at = now
                placement.save(update_fields=["status", "warmed_at", "updated_at"])
            record_runtime_audit(
                action="model.warm",
                subject_type="runtime_model",
                subject_id=str(registry.id),
                actor=actor,
                message=f"Warmup marked ready for {registry.model_name}.",
            )
            return Response({"status": "ready"})

        if action == "pause":
            AppSetting.objects.update_or_create(
                key="system.master_pause",
                defaults={
                    "value": "true",
                    "value_type": "bool",
                    "category": "performance",
                    "description": "Master pause for runtime work.",
                },
            )
            latest_backfill = RuntimeModelBackfillPlan.objects.order_by(
                "-created_at"
            ).first()
            if latest_backfill and latest_backfill.status == "running":
                latest_backfill.status = "paused"
                latest_backfill.save(update_fields=["status", "updated_at"])
            record_runtime_audit(
                action="model.pause",
                subject_type="runtime_model",
                subject_id=str(registry.id),
                actor=actor,
                message=f"Paused runtime work for {registry.model_name}.",
            )
            return Response({"status": "paused"})

        if action == "resume":
            AppSetting.objects.update_or_create(
                key="system.master_pause",
                defaults={
                    "value": "false",
                    "value_type": "bool",
                    "category": "performance",
                    "description": "Master pause for runtime work.",
                },
            )
            latest_backfill = RuntimeModelBackfillPlan.objects.order_by(
                "-created_at"
            ).first()
            if latest_backfill and latest_backfill.status == "paused":
                latest_backfill.status = "running"
                latest_backfill.save(update_fields=["status", "updated_at"])
            if registry.status == "registered":
                registry.status = "ready"
                registry.save(update_fields=["status", "updated_at"])
            record_runtime_audit(
                action="model.resume",
                subject_type="runtime_model",
                subject_id=str(registry.id),
                actor=actor,
                message=f"Resumed runtime work for {registry.model_name}.",
            )
            return Response({"status": registry.status})

        if action == "drain":
            registry.status = "draining"
            registry.draining_since = now
            registry.save(update_fields=["status", "draining_since", "updated_at"])
            if placement is not None:
                placement.status = "draining"
                placement.save(update_fields=["status", "updated_at"])
            record_runtime_audit(
                action="model.drain",
                subject_type="runtime_model",
                subject_id=str(registry.id),
                actor=actor,
                message=f"Draining {registry.model_name}.",
            )
            return Response({"status": "draining"})

        if action == "promote":
            if registry.status != "ready":
                return Response(
                    {
                        "error": "Candidates can only be promoted after download, warmup, and health checks pass."
                    },
                    status=409,
                )
            current = get_active_runtime_model(registry.task_type)
            if current and current.pk != registry.pk:
                current.role = "retired"
                current.status = "draining"
                current.draining_since = now
                current.save(
                    update_fields=["role", "status", "draining_since", "updated_at"]
                )
            dimension_changed = bool(
                current
                and current.pk != registry.pk
                and current.dimension
                and registry.dimension
                and current.dimension != registry.dimension
            )
            registry.role = "champion"
            registry.status = "ready"
            registry.promoted_at = now
            registry.save(update_fields=["role", "status", "promoted_at", "updated_at"])
            if placement is not None and placement.status != "ready":
                placement.status = "ready"
                placement.warmed_at = placement.warmed_at or now
                placement.save(update_fields=["status", "warmed_at", "updated_at"])
            AppSetting.objects.update_or_create(
                key="embedding_model",
                defaults={
                    "value": registry.model_name,
                    "value_type": "str",
                    "category": "ml",
                    "description": "Champion embedding model selected by runtime registry.",
                },
            )
            if dimension_changed and current is not None:
                RuntimeModelBackfillPlan.objects.create(
                    from_model=current,
                    to_model=registry,
                    status="queued",
                    compatibility_status="dimension_change",
                    checkpoint={},
                )
            record_runtime_audit(
                action="model.promote",
                subject_type="runtime_model",
                subject_id=str(registry.id),
                actor=actor,
                message=f"Promoted {registry.model_name} to champion.",
                metadata={"dimension_changed": dimension_changed},
            )
            return Response(
                {"status": "promoted", "dimension_changed": dimension_changed}
            )

        if action == "rollback":
            previous = (
                RuntimeModelRegistry.objects.filter(
                    task_type=registry.task_type,
                    role="retired",
                )
                .exclude(status="deleted")
                .order_by("-promoted_at", "-updated_at")
                .first()
            )
            if previous is None:
                return Response(
                    {"error": "No retired model available to roll back to."}, status=409
                )
            current = get_active_runtime_model(registry.task_type)
            if current is not None and current.pk != previous.pk:
                current.role = "retired"
                current.status = "draining"
                current.draining_since = now
                current.save(
                    update_fields=["role", "status", "draining_since", "updated_at"]
                )
            previous.role = "champion"
            previous.status = "ready"
            previous.promoted_at = now
            previous.save(update_fields=["role", "status", "promoted_at", "updated_at"])
            AppSetting.objects.update_or_create(
                key="embedding_model",
                defaults={
                    "value": previous.model_name,
                    "value_type": "str",
                    "category": "ml",
                    "description": "Champion embedding model selected by runtime registry.",
                },
            )
            record_runtime_audit(
                action="model.rollback",
                subject_type="runtime_model",
                subject_id=str(previous.id),
                actor=actor,
                message=f"Rolled back champion to {previous.model_name}.",
            )
            return Response(
                {"status": "rolled_back", "model_name": previous.model_name}
            )

        return Response(
            {"error": "Action handling fell through unexpectedly."}, status=500
        )


class RuntimeModelPlacementDeleteView(APIView):
    """DELETE /api/settings/runtime/models/placements/<id>/."""

    permission_classes = [IsAuthenticated]

    def delete(self, request, pk):
        placement = (
            RuntimeModelPlacement.objects.select_related("registry", "helper")
            .filter(pk=pk)
            .first()
        )
        if placement is None:
            return Response({"error": "Placement not found."}, status=404)
        registry = placement.registry
        if registry.role in {"champion", "candidate"}:
            return Response(
                {"error": "Champion or candidate placements cannot be deleted."},
                status=409,
            )
        if placement.status in {"warming", "draining"}:
            return Response(
                {"error": "Warming or draining placements cannot be deleted."},
                status=409,
            )
        from apps.suggestions.models import PipelineRun
        from apps.sync.models import SyncJob

        active_pipeline_runs = PipelineRun.objects.filter(
            run_state__in={"queued", "running"}
        ).exists()
        active_or_resumable_sync_jobs = (
            SyncJob.objects.filter(status__in={"pending", "running", "paused"}).exists()
            or SyncJob.objects.filter(is_resumable=True)
            .exclude(status__in={"completed", "failed", "cancelled"})
            .exists()
        )
        active_backfill = (
            RuntimeModelBackfillPlan.objects.filter(
                status__in={"queued", "running", "paused"}
            )
            .filter(from_model=registry)
            .exists()
            or RuntimeModelBackfillPlan.objects.filter(
                status__in={"queued", "running", "paused"}
            )
            .filter(to_model=registry)
            .exists()
        )
        if active_pipeline_runs or active_or_resumable_sync_jobs or active_backfill:
            return Response(
                {
                    "error": (
                        "This placement is blocked from deletion while active pipeline, sync, "
                        "resume, or backfill work could still reference it."
                    )
                },
                status=409,
            )
        if placement.status == "deleted":
            return Response(status=204)
        placement.status = "deleted"
        placement.save(update_fields=["status", "updated_at"])
        record_runtime_audit(
            action="model.delete",
            subject_type="runtime_model_placement",
            subject_id=str(placement.id),
            actor=getattr(request.user, "username", ""),
            message=f"Deleted retired placement for {registry.model_name}.",
            metadata={"disk_bytes": placement.disk_bytes},
        )
        return Response({"deleted": True, "reclaimed_disk_bytes": placement.disk_bytes})


class RuntimeSummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        capture_primary_hardware_snapshot()
        return Response(runtime_summary_payload())
