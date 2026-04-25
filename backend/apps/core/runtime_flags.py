"""Cached AppSetting flag reader for runtime toggles.

Goal
----
Phase 6 picks (and the FR-099..105 signals before them) ship with a
``<pick>.enabled`` AppSetting flag that operators can flip via the
Settings UI. For the toggle to actually do anything, the helper has
to consult the flag at call time. Reading ``AppSetting`` directly
on every call would be a hot-path DB query — the ranker can call
``vader_sentiment.score()`` once per candidate, which is thousands
of times per pipeline pass.

This module provides :func:`is_enabled` — a thin wrapper around the
Django cache that reads the AppSetting once per ``cache_seconds``
and returns the cached bool on subsequent calls. Default cache TTL
is 60 s, which is short enough that a Settings-UI toggle takes
effect on the next pipeline pass but long enough to keep the DB
load to one query per minute per flag.

Note: ``apps.core.feature_flags`` is a *different* module (A/B
variant rollout based on user-id hashing). This one is for runtime
boolean toggles read from AppSetting; the two don't overlap.

Cold-start safe at every layer:

- Django not initialised → returns *default*.
- AppSetting model missing → returns *default*.
- Migration not yet applied → returns *default*.
- DB unreachable → returns *default*.
- Cache backend not configured → falls back to direct read.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

#: Default cache TTL for flag reads. Short enough that a UI toggle
#: takes effect on the next pipeline pass; long enough to keep DB
#: load minimal under a hot-path consumer.
DEFAULT_CACHE_TTL_SECONDS: int = 60


def _coerce_bool(value: str | bool | int) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def is_enabled(
    key: str,
    *,
    default: bool = True,
    cache_seconds: int = DEFAULT_CACHE_TTL_SECONDS,
) -> bool:
    """Return the cached boolean value of ``AppSetting[key]``.

    Parameters
    ----------
    key
        AppSetting key, e.g. ``"vader_sentiment.enabled"``.
    default
        Returned when the row is missing, the value is malformed,
        the AppSetting model isn't reachable, or any other failure.
        Phase 6 picks default to True so a fresh install fires
        every helper out of the box.
    cache_seconds
        TTL on the cached value. Set to ``0`` to bypass the cache
        (one-shot direct read). Default 60 s.

    Returns
    -------
    bool
        True / False per the AppSetting row, or *default*.
    """
    cache_key = f"runtime_flag:{key}"
    if cache_seconds > 0:
        try:
            from django.core.cache import cache

            cached = cache.get(cache_key)
            if cached is not None:
                return bool(cached)
        except Exception:
            # Cache backend unconfigured / unavailable — fall through
            # to a direct read.
            pass

    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
    except Exception:
        return default

    if row is None or not row.value:
        # Don't cache the default — different callers can pass
        # different defaults for the same key, and we shouldn't
        # bake the first caller's default into a shared cache slot.
        return default

    result = _coerce_bool(row.value)

    if cache_seconds > 0:
        try:
            from django.core.cache import cache

            cache.set(cache_key, result, cache_seconds)
        except Exception:
            pass
    return result


def invalidate(key: str) -> None:
    """Drop the cached entry for *key* so the next read hits the DB.

    Used by settings-PUT views if they want a new value to take
    effect immediately rather than after the cache TTL expires.
    """
    try:
        from django.core.cache import cache

        cache.delete(f"runtime_flag:{key}")
    except Exception:
        pass
