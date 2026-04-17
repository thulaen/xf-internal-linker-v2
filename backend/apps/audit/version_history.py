"""
Phase DC / Gap 119 — generic version-history primitive.

Drop-in helper that any model can use to snapshot itself before
destructive edits. Paired with a REST endpoint that lists versions
and a one-click revert.

Design:
    - One shared table ``EntityVersion`` keyed by
      ``(target_type, target_id)`` — the same pattern the existing
      ``AuditEntry`` uses.
    - ``snapshot(instance)`` serialises the instance to JSON via
      Django's ``model_to_dict`` and appends a row.
    - Per-entity retention: keep at most ``MAX_VERSIONS_PER_ENTITY``
      rows (default 20) — oldest rolled off.
    - Revert is explicit — not in this module. The caller's view
      handler decides which fields to restore from a version payload;
      we don't mutate the live row automatically because some fields
      (timestamps, FK IDs) shouldn't be overwritten blindly.

This module is intentionally **not** auto-attached to a model via
signals. Opt-in keeps the surface small and prevents surprise
snapshotting for tables that handle their own immutability (e.g.
``SyncJob`` — every run is already a fresh row).
"""

from __future__ import annotations

from typing import Any

from django.db import models
from django.forms.models import model_to_dict
from django.utils import timezone

MAX_VERSIONS_PER_ENTITY = 20


class EntityVersion(models.Model):
    """A point-in-time snapshot of any model instance."""

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    target_type = models.CharField(max_length=60, db_index=True)
    target_id = models.CharField(max_length=100, db_index=True)
    #: The serialised instance at snapshot time.
    payload = models.JSONField(default=dict)
    #: Optional actor label — typically the username of the operator
    #: who triggered the edit, left blank for system-originated rows.
    actor = models.CharField(max_length=100, blank=True)
    #: Optional short note. Operators can record why they're about
    #: to change the entity.
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        app_label = "audit"
        verbose_name = "Entity Version"
        verbose_name_plural = "Entity Versions"
        ordering = ["-created_at"]
        indexes = [
            models.Index(
                fields=["target_type", "target_id", "-created_at"],
                name="audit_ev_target_created_idx",
            ),
        ]

    def __str__(self) -> str:
        return (
            f"{self.target_type}:{self.target_id} @ {self.created_at:%Y-%m-%d %H:%M:%S}"
        )


def snapshot(
    target_type: str,
    target_id: str | int,
    instance: models.Model,
    *,
    actor: str = "",
    note: str = "",
) -> EntityVersion:
    """Persist a snapshot and prune older rows if we exceed the cap.

    Returns the created ``EntityVersion`` row.
    """
    payload: dict[str, Any] = model_to_dict(instance)
    # ``model_to_dict`` returns datetime / date fields as native
    # objects; JSONField serialises those fine since Django 5, but
    # we coerce everything to JSON-safe via the encoder to be certain.
    row = EntityVersion.objects.create(
        target_type=target_type,
        target_id=str(target_id),
        payload=_json_safe(payload),
        actor=actor,
        note=note,
    )
    _prune(target_type, str(target_id))
    return row


def list_versions(target_type: str, target_id: str | int) -> list[EntityVersion]:
    return list(
        EntityVersion.objects.filter(
            target_type=target_type, target_id=str(target_id)
        ).order_by("-created_at")
    )


def _prune(target_type: str, target_id: str) -> None:
    qs = EntityVersion.objects.filter(
        target_type=target_type, target_id=target_id
    ).order_by("-created_at")
    count = qs.count()
    if count <= MAX_VERSIONS_PER_ENTITY:
        return
    # Use values_list then delete() on ids to avoid LIMIT-then-DELETE
    # quirks in some databases.
    stale_ids = list(qs.values_list("id", flat=True)[MAX_VERSIONS_PER_ENTITY:])
    if stale_ids:
        EntityVersion.objects.filter(id__in=stale_ids).delete()


def _json_safe(value: Any) -> Any:
    """Best-effort coerce datetimes / dates / UUIDs to str.

    Mirrors the default behaviour of ``DjangoJSONEncoder`` without
    bringing the serialiser inline — the ``JSONField`` on the model
    will finish the job.
    """
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_json_safe(v) for v in value]
    if isinstance(value, (timezone.datetime, timezone.timedelta)):
        return str(value)
    return value
