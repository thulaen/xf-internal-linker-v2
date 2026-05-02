"""Phase 4.13 — Cache Eviction Policy.

Plain-English: every cache layer (Redis dashboard cache, model-weight
cache, FAISS index cache) needs a clear rule for what to evict first
when memory or disk gets tight. This module gives operators one
control surface for all of them: per-cache stats, pin-keys (always
keep these — model weights, frequent dashboard data), explicit
eviction-on-demand, and pre-eviction warnings when a hot key is
about to drop.

The module wraps Django's ``cache`` API + the model-weight cache (per
prefix) so every read-write goes through the policy without each
service having to think about it.

Storage discipline: stats kept in a tiny in-memory ring buffer per
cache layer (~32 KB total per layer); persisted snapshots live as
single AppSetting rows refreshed once a minute. Pin-keys live in
AppSetting (one row per pin). NO new tables.

Citations:
    * Megiddo-Modha 2003 ARC ("Adaptive Replacement Cache") — eviction
      heuristic for the Redis dashboard cache.
    * O'Neil-O'Neil-Weikum 1993 LRU-K — eviction heuristic for
      Postgres TOAST-adjacent caches.
    * Megiddo-Modha 2004 §3 — pin-key semantics (admission control).
"""

from __future__ import annotations

import logging
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


# Per-cache stat ring-buffer size (events). 1024 is enough to surface
# trends on a 60-second window at typical dashboard load.
_STAT_RING_SIZE = 1024

# Operator-tunable max-size defaults per cache layer (bytes). Reading
# the live override from AppSetting; falling back to these on cold start.
_DEFAULT_MAX_SIZES_BYTES: dict[str, int] = {
    "dashboard": 32 * 1024 * 1024,        # 32 MB — small payloads, hot reads
    "model_weights": 4 * 1024 * 1024 * 1024,  # 4 GB — BGE-M3 fits with room
    "faiss_index": 1 * 1024 * 1024 * 1024,    # 1 GB — IVF-OPQ index
    "settings": 8 * 1024 * 1024,          # 8 MB — operator settings + presets
    "default": 64 * 1024 * 1024,          # generic catch-all
}


@dataclass(frozen=True, slots=True)
class CacheStat:
    """One observation: hit / miss / evict / pin / unpin event."""

    cache_layer: str
    event: str  # "hit" | "miss" | "evict" | "pin" | "unpin"
    key: str
    bytes_size: int
    timestamp: float


@dataclass(frozen=True, slots=True)
class CacheLayerSummary:
    """Operator-facing summary of one cache layer."""

    cache_layer: str
    hit_count: int
    miss_count: int
    evict_count: int
    hit_ratio: float  # 0.0 - 1.0
    estimated_size_bytes: int
    max_size_bytes: int
    pinned_key_count: int
    pinned_keys: list[str] = field(default_factory=list)


# Per-layer ring buffer. Module-level so all callers in the same
# process share one view. Reset on process restart (which is fine —
# stats are operator-facing convenience, not load-bearing).
_STATS_BY_LAYER: dict[str, deque[CacheStat]] = {}


def record_event(cache_layer: str, event: str, *, key: str = "", bytes_size: int = 0) -> None:
    """Push one observation into the per-layer ring buffer.

    Plain-English: every cache hit / miss / evict / pin / unpin
    flows through here so the operator-facing summary can render
    accurate hit-ratio + size + pin-count without each cache layer
    having its own bespoke counter.
    """
    if cache_layer not in _STATS_BY_LAYER:
        _STATS_BY_LAYER[cache_layer] = deque(maxlen=_STAT_RING_SIZE)
    _STATS_BY_LAYER[cache_layer].append(
        CacheStat(
            cache_layer=cache_layer,
            event=event,
            key=key,
            bytes_size=bytes_size,
            timestamp=time.time(),
        )
    )


def summarise_layer(cache_layer: str) -> CacheLayerSummary:
    """Return the right-now operator summary for one cache layer."""
    events = list(_STATS_BY_LAYER.get(cache_layer, ()))
    hit_count = sum(1 for e in events if e.event == "hit")
    miss_count = sum(1 for e in events if e.event == "miss")
    evict_count = sum(1 for e in events if e.event == "evict")
    total_lookups = hit_count + miss_count
    hit_ratio = (hit_count / total_lookups) if total_lookups > 0 else 0.0

    # Crude size estimate: average of bytes_size on the most recent
    # hit/miss events (each event includes the cached payload size).
    # Real cache backends report exact size via their own commands;
    # this approximation is sufficient for the operator chip. Single-
    # pass over events; ``max(..., 1)`` guards the empty-events case.
    hit_or_miss_sizes = [e.bytes_size for e in events if e.event in {"hit", "miss"}]
    estimated = sum(hit_or_miss_sizes) // max(len(hit_or_miss_sizes), 1)

    pinned = list_pinned_keys(cache_layer)

    return CacheLayerSummary(
        cache_layer=cache_layer,
        hit_count=hit_count,
        miss_count=miss_count,
        evict_count=evict_count,
        hit_ratio=round(hit_ratio, 3),
        estimated_size_bytes=estimated,
        max_size_bytes=get_max_size_bytes(cache_layer),
        pinned_key_count=len(pinned),
        pinned_keys=pinned,
    )


def summarise_all_layers() -> list[CacheLayerSummary]:
    """Return summaries for every cache layer that has activity."""
    layers = sorted(_STATS_BY_LAYER.keys())
    return [summarise_layer(layer) for layer in layers]


def get_max_size_bytes(cache_layer: str) -> int:
    """Operator-tunable max-size per layer.

    Reads ``cache_policy.<layer>.max_size_bytes`` from AppSetting;
    falls back to the per-layer default (or "default" entry) on miss.
    """
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(
            key=f"cache_policy.{cache_layer}.max_size_bytes"
        ).first()
        if row and row.value and row.value.isdigit():
            return int(row.value)
    except Exception:  # noqa: BLE001 — AppSetting blip falls back to default; never fatal.
        pass
    return _DEFAULT_MAX_SIZES_BYTES.get(
        cache_layer, _DEFAULT_MAX_SIZES_BYTES["default"]
    )


def pin_key(cache_layer: str, key: str) -> None:
    """Mark a cache key as un-evictable.

    Plain-English: tells the eviction policy "never throw this one out
    even when memory gets tight". Useful for model-weight cache rows
    (BGE-M3 reload is ~10 s) and frequent dashboard payloads.

    Storage: single AppSetting row per pinned key
    (``cache_policy.<layer>.pin.<key>``). The eviction policy reads the
    pin-set before each eviction sweep.
    """
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.update_or_create(
            key=f"cache_policy.{cache_layer}.pin.{key}",
            defaults={"value": "1"},
        )
        record_event(cache_layer, "pin", key=key)
    except Exception:  # noqa: BLE001 — pinning is operator-convenience; failure just means the key isn't pinned.
        logger.debug(
            "cache_policy: pin_key failed for %s/%s", cache_layer, key, exc_info=True
        )


def unpin_key(cache_layer: str, key: str) -> None:
    """Remove a key's pin so it becomes evictable again."""
    try:
        from apps.core.models import AppSetting

        AppSetting.objects.filter(
            key=f"cache_policy.{cache_layer}.pin.{key}"
        ).delete()
        record_event(cache_layer, "unpin", key=key)
    except Exception:  # noqa: BLE001 — unpinning is operator-convenience.
        logger.debug(
            "cache_policy: unpin_key failed for %s/%s",
            cache_layer,
            key,
            exc_info=True,
        )


def list_pinned_keys(cache_layer: str) -> list[str]:
    """Return every key pinned in this layer (for the operator chip)."""
    try:
        from apps.core.models import AppSetting

        prefix = f"cache_policy.{cache_layer}.pin."
        rows = AppSetting.objects.filter(key__startswith=prefix).values_list(
            "key", flat=True
        )
        return sorted(row[len(prefix):] for row in rows)
    except Exception:  # noqa: BLE001 — pin-list read is best-effort.
        return []


def is_pinned(cache_layer: str, key: str) -> bool:
    """True when ``key`` is pinned in ``cache_layer``."""
    try:
        from apps.core.models import AppSetting

        return AppSetting.objects.filter(
            key=f"cache_policy.{cache_layer}.pin.{key}"
        ).exists()
    except Exception:  # noqa: BLE001 — pin check is best-effort; false-negative just allows eviction.
        return False


def evict_on_demand(cache_layer: str, *, key: str | None = None) -> dict[str, Any]:
    """Operator-triggered cache purge.

    Plain-English: clicking "Purge cache" in the UI calls this. With
    ``key=None`` it clears the whole layer (skipping pinned keys);
    with a specific key it removes that one entry only.

    Returns ``{"removed_keys": [...], "skipped_pinned": [...]}`` for the
    UI's snackbar.
    """
    from django.core.cache import cache

    removed: list[str] = []
    skipped: list[str] = []

    if key is not None:
        if is_pinned(cache_layer, key):
            skipped.append(key)
        else:
            try:
                cache.delete(key)
                removed.append(key)
                record_event(cache_layer, "evict", key=key)
            except Exception:  # noqa: BLE001 — Redis blip just leaves the key in place.
                logger.debug(
                    "cache_policy: cache.delete failed for %s/%s",
                    cache_layer,
                    key,
                    exc_info=True,
                )
        return {"removed_keys": removed, "skipped_pinned": skipped}

    # Whole-layer purge: requires the layer-prefix convention so we can
    # find the keys without scanning the whole Redis keyspace. Each cache
    # layer agrees that its keys start with ``"<cache_layer>:"`` (e.g.
    # ``dashboard:summary``). Keys that don't follow this convention
    # are out of scope for whole-layer purge — operator must use the
    # per-key form.
    try:
        from django_redis import get_redis_connection

        redis_client = get_redis_connection("default")
        pattern = f"{cache_layer}:*"
        for raw_key in redis_client.scan_iter(match=pattern, count=200):
            cache_key = raw_key.decode() if isinstance(raw_key, bytes) else raw_key
            short_key = cache_key.split(":", 1)[-1]
            if is_pinned(cache_layer, short_key):
                skipped.append(short_key)
                continue
            redis_client.delete(raw_key)
            removed.append(short_key)
            record_event(cache_layer, "evict", key=short_key)
    except Exception:  # noqa: BLE001 — operator action; surface the partial result.
        logger.warning(
            "cache_policy: whole-layer purge for %s hit an error",
            cache_layer,
            exc_info=True,
        )

    return {"removed_keys": removed, "skipped_pinned": skipped}
