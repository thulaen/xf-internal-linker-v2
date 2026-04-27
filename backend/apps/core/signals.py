"""
Realtime broadcast signals for the core app.

Phase R1.3 of the master plan. AppSetting rows change when an operator
toggles Performance Mode, Master Pause, weight tune schedule, etc. The
existing REST endpoint already serves the values; this signal pushes the
new value to every open tab the instant it lands, so two staff members
working in parallel don't step on each other.

Topic `settings.runtime` is staff-only — enforced in
apps/realtime/permissions.py.

## Why we filter by execution context

The signal *would* fire on every AppSetting write, including hundreds of
internal housekeeping writes from Celery beat schedules (telemetry
last-sync stamps, performance-mode auto-revert, embedding state, etc.).
That spam reaches every open Settings page as a misleading "Settings
updated from another tab" toast.

The architectural distinguisher: user-initiated writes flow through a
Django web request (ASGI / WSGI), where `celery.current_task()` returns
None. Celery worker writes always have a non-None current_task. A single
upstream check eliminates the entire class of housekeeping noise without
needing a deny-list of keys, categories, or callsites — any future
Celery task that touches AppSetting is auto-excluded.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.realtime.services import broadcast

from .models import AppSetting

logger = logging.getLogger(__name__)

TOPIC = "settings.runtime"


def _is_celery_context() -> bool:
    """Return True when running inside a Celery task (worker or beat).

    Used to suppress AppSetting realtime broadcasts originating from
    background jobs — those are housekeeping writes, not user-initiated
    edits, and broadcasting them spams every open Settings page.

    Django request handlers (the path user-facing PUT views take) are
    NOT Celery contexts, so legitimate user saves still broadcast.
    """
    try:
        from celery._state import get_current_task

        return get_current_task() is not None
    except ImportError:
        # Celery missing entirely — never a Celery context.
        return False
    except Exception:  # pragma: no cover - defensive
        # If introspection fails for any reason, default to "not Celery"
        # so user broadcasts still work. Worst-case: a stray Celery write
        # leaks through; same behaviour as before this filter existed.
        return False


def _serialize(setting: AppSetting) -> dict:
    """
    Hand-rolled payload (no DRF serializer exists for AppSetting today).
    Matches the shape the frontend Settings page consumes via
    `GET /api/settings/` — keep in sync if that endpoint changes.
    """
    return {
        "key": setting.key,
        "value": setting.value,
        "value_type": setting.value_type,
        "category": setting.category,
        "description": setting.description,
        "updated_at": setting.updated_at.isoformat() if setting.updated_at else None,
    }


@receiver(post_save, sender=AppSetting, dispatch_uid="realtime.app_setting.saved")
def _on_app_setting_saved(
    sender, instance: AppSetting, created: bool, **kwargs: object
) -> None:
    if _is_celery_context():
        # Background housekeeping write — silently skip. See module
        # docstring for rationale. Future Celery tasks get this for free.
        return
    broadcast(
        TOPIC,
        event="setting.created" if created else "setting.updated",
        payload=_serialize(instance),
    )


@receiver(post_delete, sender=AppSetting, dispatch_uid="realtime.app_setting.deleted")
def _on_app_setting_deleted(sender, instance: AppSetting, **kwargs: object) -> None:
    if _is_celery_context():
        return
    broadcast(
        TOPIC,
        event="setting.deleted",
        payload={"key": instance.key},
    )
