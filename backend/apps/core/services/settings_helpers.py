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
    """Operator-tier → recommended-preset tier → hardcoded fallback (bool)."""
    raw = _read_operator(key)
    if raw is not None:
        return raw.strip().lower() in {"true", "1", "yes", "on"}
    try:
        from apps.suggestions.recommended_weights import recommended_bool

        return recommended_bool(key)
    except KeyError:
        return fallback


def setting_str(key: str, fallback: str) -> str:
    """Operator-tier → recommended-preset tier → hardcoded fallback (str)."""
    raw = _read_operator(key)
    if raw is not None:
        return raw
    try:
        from apps.suggestions.recommended_weights import recommended_str

        return recommended_str(key)
    except (KeyError, Exception):
        return fallback
