"""Core settings readers and coercers (Layer 1 + 2 + 3).

Split from settings_helpers.py on 2026-05-10 to stay under the 1500-line cap.
This module contains the low-level logic for reading AppSettings and normalizing values.
"""

from __future__ import annotations

import logging
import math
from typing import TypeVar

from apps.api.query_params import coerce_bool
from apps.suggestions.recommended_weights import (
    recommended_bool,
    recommended_float,
    recommended_int,
    recommended_str,
)

logger = logging.getLogger(__name__)

T = TypeVar("T", int, float, bool, str)


def _read_operator(key: str) -> str | None:
    """Return the operator's AppSetting value or None if not set."""
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
        if row is None or row.value in (None, ""):
            return None
        return str(row.value)
    except Exception:
        logger.debug(
            "settings_base: AppSetting read failed for %s", key, exc_info=True
        )
        return None


def _get_app_setting_value(key: str, default: str | None = None) -> str | None:
    """Generic AppSetting accessor."""
    from apps.core.models import AppSetting

    setting = AppSetting.objects.filter(key=key).first()
    if setting is None:
        return default
    return setting.value


def setting_int(key: str, fallback: int) -> int:
    """Operator-tier → recommended-preset tier → hardcoded fallback (int)."""
    raw = _read_operator(key)
    if raw is not None:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            logger.debug(
                "settings_base: setting_int(%s) bad operator value %r; falling back to preset",
                key,
                raw,
            )
    try:
        return recommended_int(key)
    except KeyError:
        return fallback


def setting_float(key: str, fallback: float) -> float:
    """Operator-tier → recommended-preset tier → hardcoded fallback (float)."""
    raw = _read_operator(key)
    if raw is not None:
        try:
            return float(raw)
        except (TypeError, ValueError):
            logger.debug(
                "settings_base: setting_float(%s) bad operator value %r; falling back to preset",
                key,
                raw,
            )
    try:
        return recommended_float(key)
    except KeyError:
        return fallback


def setting_bool(key: str, fallback: bool) -> bool:
    """Operator-tier → recommended-preset tier → hardcoded fallback (bool)."""
    raw = _read_operator(key)
    if raw is not None:
        return coerce_bool(raw, default=fallback)
    try:
        return recommended_bool(key)
    except KeyError:
        return fallback


def setting_str(key: str, fallback: str) -> str:
    """Operator-tier → recommended-preset tier → hardcoded fallback (str)."""
    raw = _read_operator(key)
    if raw is not None:
        return raw
    try:
        return recommended_str(key)
    except KeyError:
        return fallback
    except Exception:
        logger.exception("Failed to read recommended setting for %s", key)
        return fallback


# ── PUT-payload coercers (Strict) ───────────────────────────────────

def coerce_setting_float(
    payload: dict,
    current: dict,
    key: str,
    *,
    require_finite: bool = True,
) -> float:
    """Coerce payload[key] (with current[key] fallback) to float. Raises ValueError."""
    value = payload.get(key, current[key])
    try:
        coerced = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric.") from exc
    if require_finite and not math.isfinite(coerced):
        raise ValueError(f"{key} must be finite.")
    return coerced


def coerce_setting_int(payload: dict, current: dict, key: str) -> int:
    """Coerce payload[key] (with current[key] fallback) to int. Raises ValueError."""
    value = payload.get(key, current[key])
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be an integer.") from exc


def coerce_setting_bool(
    payload: dict,
    current: dict,
    key: str,
    *,
    default: bool = False,
) -> bool:
    """Coerce payload[key] (with current[key] fallback) to bool."""
    value = payload.get(key, current[key])
    return coerce_bool(value, default=default)


def enforce_bounds(
    validated: dict,
    bounds: dict[str, tuple[float, float]],
) -> None:
    """Raise ValueError if any validated[key] is outside bounds[key]."""
    for key, (minimum, maximum) in bounds.items():
        value = validated[key]
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")


# ── Clamping variants ──────────────────────────────────────────────

def coerce_clamp_float(
    payload: dict,
    current: dict,
    key: str,
    lo: float,
    hi: float,
) -> float:
    """Coerce payload[key] and clamp to [lo, hi]. Silently falls back on bad input."""
    val = payload.get(key, current.get(key))
    try:
        coerced = float(val)
    except (TypeError, ValueError):
        coerced = float(current.get(key, 0.0))
    return max(lo, min(hi, coerced))


def coerce_clamp_int(
    payload: dict,
    current: dict,
    key: str,
    lo: int,
    hi: int,
) -> int:
    """Coerce payload[key] and clamp to [lo, hi]."""
    val = payload.get(key, current.get(key))
    try:
        coerced = int(val)
    except (TypeError, ValueError):
        coerced = int(current.get(key, 0))
    return max(lo, min(hi, coerced))


def coerce_lenient_bool(payload: dict, current: dict, key: str) -> bool:
    """Lenient variant of coerce_setting_bool."""
    val = payload.get(key, current.get(key))
    return coerce_bool(val, default=False)


# ── Two-tier readers (operator → default) ──────────────────────────

def read_app_setting_float(
    key: str,
    default: float,
    *,
    require_finite: bool = True,
) -> float:
    """Read a float AppSetting with safe fallback. Two-tier: operator → default."""
    raw = _read_operator(key)
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if require_finite and not math.isfinite(value):
        return default
    return value


def read_app_setting_int(key: str, default: int) -> int:
    """Read an int AppSetting with safe fallback. Two-tier: operator → default."""
    raw = _read_operator(key)
    if raw is None:
        return default
    try:
        return int(raw)
    except (TypeError, ValueError):
        return default


def read_app_setting_bool(key: str, default: bool) -> bool:
    """Read a bool AppSetting with safe fallback. Two-tier: operator → default."""
    raw = _read_operator(key)
    if raw is None:
        return default
    return coerce_bool(raw, default=default)


# ── Strict Coercers (used by specific feature validators) ───────────

def _coerce_float_strict(value: object, *, key: str) -> float:
    try:
        coerced = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric.") from exc
    if not math.isfinite(coerced):
        raise ValueError(f"{key} must be finite.")
    return coerced


def _coerce_int_strict(value: object, *, key: str, minimum: int, maximum: int) -> int:
    try:
        coerced = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be a whole number.") from exc
    if coerced < minimum or coerced > maximum:
        raise ValueError(f"{key} must be between {minimum} and {maximum}.")
    return coerced


def _coerce_bool_strict(value: object, *, key: str) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        from apps.api.query_params import FALSY_STRING_VALUES, TRUTHY_STRING_VALUES
        if lowered in TRUTHY_STRING_VALUES:
            return True
        if lowered in FALSY_STRING_VALUES:
            return False
    raise ValueError(f"{key} must be true or false.")
