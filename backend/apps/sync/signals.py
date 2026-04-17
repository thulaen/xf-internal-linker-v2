"""
Realtime broadcast signals for the sync app.

Phase R1.3 of the master plan.

Topics:
- `jobs.history` — SyncJob lifecycle (queue + history table on /jobs).
  Replaces the 30s polling that runs on the Jobs page today. Per-job
  progress (in-flight percent, ML queue counts) continues to flow through
  the existing `/ws/jobs/<job_id>/` WebSocket — we don't touch that.
- `webhooks.receipts` — WebhookReceipt audit log.
  Replaces the 10s polling on the webhook log.

Broadcasts use the existing DRF serializers so WebSocket payload shape
matches the HTTP shape; the frontend just merges received rows into its
existing arrays without a separate mapping.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.realtime.services import broadcast

from .models import SyncJob, WebhookReceipt
from .serializers import SyncJobSerializer, WebhookReceiptSerializer

logger = logging.getLogger(__name__)

TOPIC_JOBS = "jobs.history"
TOPIC_WEBHOOKS = "webhooks.receipts"


# ── SyncJob ────────────────────────────────────────────────────────


@receiver(post_save, sender=SyncJob, dispatch_uid="realtime.sync_job.saved")
def _on_sync_job_saved(sender, instance: SyncJob, created: bool, **kwargs: object) -> None:
    broadcast(
        TOPIC_JOBS,
        event="job.created" if created else "job.updated",
        payload=SyncJobSerializer(instance).data,
    )


@receiver(post_delete, sender=SyncJob, dispatch_uid="realtime.sync_job.deleted")
def _on_sync_job_deleted(sender, instance: SyncJob, **kwargs: object) -> None:
    broadcast(
        TOPIC_JOBS,
        event="job.deleted",
        payload={"job_id": str(instance.job_id)},
    )


# ── WebhookReceipt ────────────────────────────────────────────────


@receiver(post_save, sender=WebhookReceipt, dispatch_uid="realtime.webhook_receipt.saved")
def _on_webhook_receipt_saved(
    sender, instance: WebhookReceipt, created: bool, **kwargs: object
) -> None:
    broadcast(
        TOPIC_WEBHOOKS,
        event="receipt.created" if created else "receipt.updated",
        payload=WebhookReceiptSerializer(instance).data,
    )


@receiver(
    post_delete, sender=WebhookReceipt, dispatch_uid="realtime.webhook_receipt.deleted"
)
def _on_webhook_receipt_deleted(
    sender, instance: WebhookReceipt, **kwargs: object
) -> None:
    broadcast(
        TOPIC_WEBHOOKS,
        event="receipt.deleted",
        payload={"receipt_id": str(instance.receipt_id)},
    )
