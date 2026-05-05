"""Three-tier settings access helper (Phase 4 tech-debt extraction).

Many services (``passage_relevance``, ``faiss_index``, ``feedback_relevance``,
etc.) reach for the same three-tier settings pattern:

    1. Operator-set ``AppSetting`` row, if present.
    2. Recommended-preset value via ``recommended_int / _str / _bool / _float``.
    3. Hardcoded fallback supplied by the caller.

That pattern was duplicated in `passage_relevance.py:_setting_int / _bool /
_float` (~30 lines). Extracting it here lets every service collapse the
boilerplate to a single import + call.

Three-tier semantics is intentional: the recommended-preset middle layer
matters because every Wave-2 ranking signal starts at the spec's prior
weight. ``AppSetting.get_int()`` (Django's existing helper) is two-tier
(operator → fallback) and would lose the preset middle layer, so we don't
just call it directly.

Citation: pattern derived from the FR-099–FR-105 settings flow + the
Recommended-preset migration discipline documented in CLAUDE.md.
"""

from __future__ import annotations

import logging
from typing import TypeVar

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
        logger.debug("settings_helpers: AppSetting read failed for %s", key, exc_info=True)
        return None


def setting_int(key: str, fallback: int) -> int:
    """Operator-tier → recommended-preset tier → hardcoded fallback (int)."""
    raw = _read_operator(key)
    if raw is not None:
        try:
            return int(float(raw))
        except (TypeError, ValueError):
            # Bad operator value falls through to the recommended
            # preset; debug-log so the operator can find the bad row.
            logger.debug(
                "settings_helpers: setting_int(%s) bad operator value %r; "
                "falling back to recommended preset",
                key,
                raw,
            )
    try:
        from apps.suggestions.recommended_weights import recommended_int

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
                "settings_helpers: setting_float(%s) bad operator value %r; "
                "falling back to recommended preset",
                key,
                raw,
            )
    try:
        from apps.suggestions.recommended_weights import recommended_float

        return recommended_float(key)
    except KeyError:
        return fallback


def setting_bool(key: str, fallback: bool) -> bool:
    """Operator-tier → recommended-preset tier → hardcoded fallback (bool).

    Refactor 2026-05-04: shared coerce_bool from apps.api.query_params.
    """
    from apps.api.query_params import coerce_bool

    raw = _read_operator(key)
    if raw is not None:
        return coerce_bool(raw, default=fallback)
    try:
        from apps.suggestions.recommended_weights import recommended_bool

        return recommended_bool(key)
    except KeyError:
        return fallback


def setting_str(key: str, fallback: str) -> str:
    """Operator-tier → recommended-preset tier → hardcoded fallback (str).

    The preset-tier exception is intentionally broad: any failure (module
    not yet loaded during migration, missing key, import error) falls
    through to the hardcoded fallback so settings reads NEVER raise.
    Logs at debug so operators can grep for missing preset keys.
    """
    raw = _read_operator(key)
    if raw is not None:
        return raw
    try:
        from apps.suggestions.recommended_weights import recommended_str

        return recommended_str(key)
    except KeyError:
        logger.debug("settings_helpers: setting_str(%s) missing from recommended preset", key)
        return fallback
    except Exception:
        logger.debug(
            "settings_helpers: setting_str(%s) preset import failed; using fallback",
            key, exc_info=True,
        )
        return fallback


# ---------------------------------------------------------------------------
# Validate-side coercers (PUT-payload validation, not settings reads).
#
# These four helpers replace ~17 duplicated _coerce_int / _coerce_float /
# _coerce_bool closures previously inlined in apps/core/views.py validators.
# Each closure was 7-9 lines of identical boilerplate — exactly the kind of
# "duplicate 6+ line block" THINK-BEFORE-YOU-CODE forbids. Extracting here
# also fixes a sister bug in _validate_feedback_rerank_settings, which
# rolled its own bool-coercer that didn't accept "y" / "Y" the way the
# project-wide coerce_bool does.
# ---------------------------------------------------------------------------


def coerce_setting_float(
    payload: dict,
    current: dict,
    key: str,
    *,
    require_finite: bool = True,
) -> float:
    """Coerce ``payload[key]`` (with ``current[key]`` fallback) to float.

    Raises:
        ValueError: payload value cannot be parsed, or (if require_finite) is
            inf/NaN. Error message names the offending key so the operator
            sees which field failed in the API response.
    """
    import math

    value = payload.get(key, current[key])
    try:
        coerced = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{key} must be numeric.") from exc
    if require_finite and not math.isfinite(coerced):
        raise ValueError(f"{key} must be finite.")
    return coerced


def coerce_setting_int(payload: dict, current: dict, key: str) -> int:
    """Coerce ``payload[key]`` (with ``current[key]`` fallback) to int.

    Raises:
        ValueError: payload value cannot be parsed as int. Error message
            names the offending key.
    """
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
    """Coerce ``payload[key]`` (with ``current[key]`` fallback) to bool.

    Delegates to ``apps.api.query_params.coerce_bool`` so all string
    truthiness rules (``y``/``yes``/``true``/``1``/``on``, case-insensitive)
    are consistent across the codebase.
    """
    from apps.api.query_params import coerce_bool

    value = payload.get(key, current[key])
    return coerce_bool(value, default=default)


def enforce_bounds(
    validated: dict,
    bounds: dict[str, tuple[float, float]],
) -> None:
    """Raise ValueError if any ``validated[key]`` is outside ``bounds[key]``.

    Replaces the duplicated four-line ``for key, (lo, hi) in bounds.items()``
    loop and the ~17 inline ``"x must be between A and B"`` checks scattered
    through ``apps/core/views.py``. Bounds are inclusive on both ends.
    """
    for key, (minimum, maximum) in bounds.items():
        value = validated[key]
        if value < minimum or value > maximum:
            raise ValueError(f"{key} must be between {minimum} and {maximum}.")


# ---------------------------------------------------------------------------
# Lenient (clamping) variants — used by ``_validate_value_model_settings``
# and similar endpoints where bad operator input should be silently clamped
# rather than rejected. The strict raise-on-error helpers above are the
# default; reach for these only when the spec explicitly says "clamp".
# ---------------------------------------------------------------------------


def coerce_clamp_float(
    payload: dict,
    current: dict,
    key: str,
    lo: float,
    hi: float,
) -> float:
    """Coerce ``payload[key]`` (with ``current[key]`` fallback) and clamp to ``[lo, hi]``.

    Lenient: bad strings fall back to ``current.get(key, 0.0)`` instead of
    raising. Used by value-model settings where the spec is "clamp don't reject".
    """
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
    """Coerce ``payload[key]`` (with ``current[key]`` fallback) and clamp to ``[lo, hi]``.

    Lenient int variant: bad input falls back to ``current.get(key, 0)``.
    """
    val = payload.get(key, current.get(key))
    try:
        coerced = int(val)
    except (TypeError, ValueError):
        coerced = int(current.get(key, 0))
    return max(lo, min(hi, coerced))


def coerce_lenient_bool(payload: dict, current: dict, key: str) -> bool:
    """Coerce ``payload[key]`` (with ``current.get(key)`` fallback) to bool.

    Lenient variant of ``coerce_setting_bool`` — uses ``current.get()`` so
    a missing-from-current key doesn't KeyError. Used by the value-model
    validator and any other endpoint that accepts partial PUTs.
    """
    from apps.api.query_params import coerce_bool

    val = payload.get(key, current.get(key))
    return coerce_bool(val, default=False)


# ---------------------------------------------------------------------------
# Two-tier AppSetting readers (operator → fallback, no preset middle layer).
#
# These three helpers replace ~29 duplicated _read_float / _read_int /
# _read_bool closures previously inlined in apps/core/views.py "load X
# settings from AppSetting" functions. Each closure was 5-7 lines of
# identical try/except/finite-check boilerplate.
#
# Why a separate set vs setting_int/float/bool above: those are 3-tier
# (operator → recommended-preset → fallback). The "_read_*" closures
# being replaced are deliberately 2-tier — they implement the per-feature
# defaults file (DEFAULT_*_SETTINGS dict) as the second tier rather than
# pulling from recommended_weights. Keeping the 2-tier semantic is a
# hard-correctness requirement: changing it to 3-tier would silently
# change every settings page's default values.
# ---------------------------------------------------------------------------


def read_app_setting_float(
    key: str,
    default: float,
    *,
    require_finite: bool = True,
) -> float:
    """Read a float AppSetting with safe fallback. Two-tier: operator → default.

    Returns ``default`` on parse error or (if require_finite) inf/NaN.
    No exception raised, no logging — silent fall-through is the contract.
    """
    import math

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
    from apps.api.query_params import coerce_bool

    raw = _read_operator(key)
    if raw is None:
        return default
    return coerce_bool(raw, default=default)
