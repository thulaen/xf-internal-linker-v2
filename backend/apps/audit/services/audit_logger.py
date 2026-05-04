"""Unified audit logging service."""

from __future__ import annotations

import logging
from typing import Any, Optional, Union

from django.db import models
from django.http import HttpRequest

from apps.audit.models import AuditEntry, AuditEvent

logger = logging.getLogger(__name__)

AuditTarget = Union[models.Model, str, tuple[str, str], None]


def record_audit(
    action: str,
    target: AuditTarget = None,
    detail: Optional[dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
    ip_address: Optional[str] = None,
    *,
    subject: AuditTarget = None,
    actor: str = "",
    message: str = "",
    metadata: Optional[dict[str, Any]] = None,
) -> AuditEvent:
    """Record a state-changing operator event in the unified audit table."""
    selected_target = subject if subject is not None else target
    subject_type, subject_id = _resolve_target(selected_target)
    payload = dict(metadata if metadata is not None else detail or {})
    actor = actor or _actor_from_request(request)
    ip_address = ip_address or _ip_from_request(request)
    message = message or f"{action.replace('_', ' ')} on {subject_type}"

    if not _audit_enabled():
        logger.debug("[audit] skipped because system.audit_log_enabled=false")
        return AuditEvent(
            action=action[:80],
            subject_type=subject_type[:80],
            subject_id=subject_id[:120],
            actor=actor[:150],
            message=message,
            metadata=payload,
            ip_address=ip_address,
        )

    entry = AuditEvent.objects.create(
        action=action[:80],
        subject_type=subject_type[:80],
        subject_id=subject_id[:120],
        actor=actor[:150],
        message=message,
        metadata=payload,
        ip_address=ip_address,
    )
    logger.debug("[audit] Recorded event: %s", entry)
    return entry


def record_legacy_audit(
    action: str,
    target: Union[models.Model, str, tuple[str, str]],
    detail: Optional[dict[str, Any]] = None,
    request: Optional[HttpRequest] = None,
    ip_address: Optional[str] = None,
) -> AuditEntry:
    """Compatibility writer for old AuditEntry-specific reports."""
    target_type, target_id = _resolve_target(target)
    ip_address = ip_address or _ip_from_request(request)
    entry = AuditEntry.objects.create(
        action=action,
        target_type=target_type[:50],
        target_id=target_id[:100],
        detail=detail or {},
        ip_address=ip_address,
    )
    logger.debug("[audit] Recorded legacy entry: %s", entry)
    return entry


def _resolve_target(target: AuditTarget) -> tuple[str, str]:
    if isinstance(target, models.Model):
        return target._meta.model_name, str(target.pk)
    if isinstance(target, tuple):
        return str(target[0]), str(target[1])
    if target:
        return str(target), ""
    return "system", ""


def _actor_from_request(request: Optional[HttpRequest]) -> str:
    if not request or not getattr(request, "user", None):
        return ""
    user = request.user
    if not getattr(user, "is_authenticated", False):
        return ""
    return getattr(user, "username", "") or str(getattr(user, "pk", ""))


def _ip_from_request(request: Optional[HttpRequest]) -> str | None:
    if not request:
        return None
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR")


def _audit_enabled() -> bool:
    """Audit logging is on by default; operator can disable via AppSetting.

    Refactor 2026-05-04: shared coerce_bool — was an inline copy of the
    standard 4-truthy-string parser.
    """
    from apps.api.query_params import coerce_bool

    try:
        from apps.core.models import AppSetting

        value = (
            AppSetting.objects.filter(key="system.audit_log_enabled")
            .values_list("value", flat=True)
            .first()
        )
    except Exception:  # noqa: BLE001 — AppSetting unavailable on cold-start; default to "audit on" so events aren't silently dropped.
        return True
    # Treat missing / empty value as enabled — the explicit "false"
    # opt-out is the only way to disable audit logging.
    if value is None or value == "":
        return True
    return coerce_bool(value, default=True)


record_event = record_audit

__all__ = ["record_audit", "record_event", "record_legacy_audit"]
