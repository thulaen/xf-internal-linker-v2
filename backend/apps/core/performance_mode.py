"""Canonical performance-mode helpers shared across runtime-sensitive services."""

from __future__ import annotations

import logging
import os

from django.conf import settings as django_settings

logger = logging.getLogger(__name__)

PERFORMANCE_MODE_SAFE = "safe"
PERFORMANCE_MODE_BALANCED = "balanced"
PERFORMANCE_MODE_HIGH = "high"

_MODE_ALIASES = {
    "safe": PERFORMANCE_MODE_SAFE,
    "balanced": PERFORMANCE_MODE_BALANCED,
    "standard": PERFORMANCE_MODE_BALANCED,
    "high": PERFORMANCE_MODE_HIGH,
    "high_performance": PERFORMANCE_MODE_HIGH,
}


def normalize_performance_mode(raw: str | None, *, warn: bool = True) -> str:
    """Normalize legacy and canonical mode names to one shared vocabulary."""
    if raw is None:
        return PERFORMANCE_MODE_BALANCED

    normalized = str(raw).strip().lower().replace("-", "_").replace(" ", "_")
    if not normalized:
        return PERFORMANCE_MODE_BALANCED

    canonical = _MODE_ALIASES.get(normalized)
    if canonical is not None:
        return canonical

    if warn:
        logger.warning(
            "Unknown performance mode '%s'; falling back to balanced.", raw
        )
    return PERFORMANCE_MODE_BALANCED


def get_requested_performance_mode() -> str:
    """Return the operator-requested performance mode."""
    try:
        from apps.core.models import AppSetting

        db_mode = (
            AppSetting.objects.filter(key="system.performance_mode")
            .values_list("value", flat=True)
            .first()
        )
        if db_mode not in (None, ""):
            return normalize_performance_mode(str(db_mode))
    except Exception:
        logger.debug(
            "AppSetting unavailable while resolving performance mode",
            exc_info=True,
        )

    env_mode = os.environ.get("ML_PERFORMANCE_MODE")
    if env_mode in (None, ""):
        env_mode = getattr(django_settings, "ML_PERFORMANCE_MODE", "BALANCED")
    return normalize_performance_mode(str(env_mode))


def is_high_performance_mode() -> bool:
    """Return True when the canonical requested mode is GPU-eligible."""
    return get_requested_performance_mode() == PERFORMANCE_MODE_HIGH
