"""
Job queue and quarantine views extracted from ``views_capacity.py``.
Part of the domain-driven decomposition to stay under the 1500-line cap.
"""

from __future__ import annotations

import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

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
        """Active + queued tasks across pipeline + sync, plus active locks."""
        from apps.pipeline.services.task_lock import get_active_locks

        return Response(
            {
                "items": (_job_queue_active_runs() + _job_queue_active_syncs()),
                "locks": get_active_locks(),
            }
        )


# ── JobQuarantineView helpers ─────────────────────────────────────


def _quarantine_records_and_run_ids() -> tuple[list[dict], set[str]]:
    """New-style: open ``QuarantineRecord`` rows."""
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
    """Legacy: ``PipelineRun.is_quarantined=True`` rows without a matching record."""
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
    """GET /api/jobs/quarantine/ — quarantined items."""

    permission_classes = [IsAuthenticated]

    def get(self, request):
        """Combined open-quarantine list — new QuarantineRecord rows + legacy."""
        records, quarantined_run_ids = _quarantine_records_and_run_ids()
        legacy = _quarantine_legacy_rows(skip_run_ids=quarantined_run_ids)
        return Response(records + legacy)
