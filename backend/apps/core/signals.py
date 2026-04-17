"""
Realtime broadcast signals for the core app.

Phase R1.3 of the master plan. AppSetting rows change when an operator
toggles Performance Mode, Master Pause, weight tune schedule, etc. The
existing REST endpoint already serves the values; this signal pushes the
new value to every open tab the instant it lands, so two staff members
working in parallel don't step on each other.

Topic `settings.runtime` is staff-only — enforced in
apps/realtime/permissions.py. The broadcast fires unconditionally; the
consumer is where the authorisation check happens.
"""

from __future__ import annotations

import logging

from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.realtime.services import broadcast

from .models import AppSetting

logger = logging.getLogger(__name__)

TOPIC = "settings.runtime"


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
    broadcast(
        TOPIC,
        event="setting.created" if created else "setting.updated",
        payload=_serialize(instance),
    )


@receiver(post_delete, sender=AppSetting, dispatch_uid="realtime.app_setting.deleted")
def _on_app_setting_deleted(
    sender, instance: AppSetting, **kwargs: object
) -> None:
    broadcast(
        TOPIC,
        event="setting.deleted",
        payload={"key": instance.key},
    )
