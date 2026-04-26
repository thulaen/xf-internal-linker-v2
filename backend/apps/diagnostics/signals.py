"""
Realtime broadcast signals for the diagnostics app.

Every time a `ServiceStatusSnapshot` or `SystemConflict` changes, the
diagnostics page needs to update without the user clicking "Run New Check".
Phase R1.1 of the approved master plan.

How it works
------------
- `post_save` on either model calls `apps.realtime.services.broadcast`.
- Payload is rendered through the existing REST serializer so the WebSocket
  shape is identical to the HTTP shape — frontend code can merge updates
  without a separate mapping.
- `ServiceStatusSnapshot` rows where `service_name == "http_worker"` are
  excluded from the broadcast because the REST view excludes them too
  (stale decommissioned http_worker row; see ISS-009 and
  `apps/diagnostics/views.py`). Without this guard a legacy http_worker
  row re-surfaces whenever it touches the DB, even though the UI filters
  it out.
- `post_delete` fires an `entity.deleted` event so the frontend can drop
  the row without a full re-fetch.

Errors from the broadcast are swallowed by `apps.realtime.services.broadcast`;
nothing here raises.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.realtime.services import broadcast

from .models import ServiceStatusSnapshot, SystemConflict
from .serializers import ServiceStatusSerializer, SystemConflictSerializer

logger = logging.getLogger(__name__)

TOPIC = "diagnostics"


# ── ServiceStatusSnapshot ──────────────────────────────────────────


@receiver(
    post_save,
    sender=ServiceStatusSnapshot,
    dispatch_uid="realtime.service_status.saved",
)
def _on_service_status_saved(
    sender, instance: ServiceStatusSnapshot, created: bool, **kwargs: object
) -> None:
    # Hide the same row the REST view hides (stale http_worker decommission leftover; ISS-009).
    if instance.service_name == "http_worker":
        return
    broadcast(
        TOPIC,
        event="service.status.created" if created else "service.status.updated",
        payload=ServiceStatusSerializer(instance).data,
    )


@receiver(
    post_delete,
    sender=ServiceStatusSnapshot,
    dispatch_uid="realtime.service_status.deleted",
)
def _on_service_status_deleted(
    sender, instance: ServiceStatusSnapshot, **kwargs: object
) -> None:
    if instance.service_name == "http_worker":
        return
    broadcast(
        TOPIC,
        event="service.status.deleted",
        payload={"id": instance.pk, "service_name": instance.service_name},
    )


# ── SystemConflict ─────────────────────────────────────────────────


@receiver(
    post_save, sender=SystemConflict, dispatch_uid="realtime.system_conflict.saved"
)
def _on_system_conflict_saved(
    sender, instance: SystemConflict, created: bool, **kwargs: object
) -> None:
    broadcast(
        TOPIC,
        event="conflict.created" if created else "conflict.updated",
        payload=SystemConflictSerializer(instance).data,
    )


@receiver(
    post_delete, sender=SystemConflict, dispatch_uid="realtime.system_conflict.deleted"
)
def _on_system_conflict_deleted(
    sender, instance: SystemConflict, **kwargs: object
) -> None:
    broadcast(
        TOPIC,
        event="conflict.deleted",
        payload={"id": instance.pk},
    )
