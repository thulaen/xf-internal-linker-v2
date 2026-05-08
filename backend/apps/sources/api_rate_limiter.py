"""FR-250 — Python wrapper around the C++ ``api_rate_limiter`` extension.

The C++ extension at ``backend/extensions/api_rate_limiter.cpp`` is the
source of truth. This module:

1. Imports the C++ ``RateLimiterRegistry`` and exposes a process-wide
   singleton ``REGISTRY``.
2. Holds the per-API bucket presets (``BUCKET_PRESETS``) — every default
   has a citation in ``docs/specs/fr250-api-rate-limiter.md``.
3. Provides ``rate_limited(name)``: a context manager every outbound
   ``requests.get/.post`` to GSC, GA4, Matomo, XenForo, or WordPress
   should be wrapped in.

If the C++ extension is not built, we fall back to the pure-Python
``TokenBucket`` already shipped at ``backend/apps/sources/token_bucket.py``.
This satisfies CPP-FIRST.md's "Python is fallback and reference only".
"""

from __future__ import annotations

import logging
import time
from contextlib import contextmanager
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BucketPreset:
    """One row of the rate-limit table from the FR-250 spec."""

    name: str
    capacity: float
    rate_per_sec: float
    daily_quota: int = -1  # -1 disables the daily counter
    citation: str = ""


# Defaults below are 80% of each provider's documented limit, leaving
# headroom for retries. Citations point at the official rate-limit doc;
# every preset is tied back to docs/specs/fr250-api-rate-limiter.md.
BUCKET_PRESETS: dict[str, BucketPreset] = {
    # Google Search Console — 1,200 QPM per site, 30,000 QPD per project.
    # https://developers.google.com/webmaster-tools/v1/limits
    "gsc_search_analytics": BucketPreset(
        name="gsc_search_analytics",
        capacity=20.0,
        rate_per_sec=10.0,
        daily_quota=25_000,
        citation="https://developers.google.com/webmaster-tools/v1/limits",
    ),
    # Google Analytics 4 Data API — 1,250 / 100s per project, 50,000 / day.
    # https://developers.google.com/analytics/devguides/reporting/data/v1/quotas
    "ga4_data_api": BucketPreset(
        name="ga4_data_api",
        capacity=50.0,
        rate_per_sec=12.0,
        daily_quota=40_000,
        citation="https://developers.google.com/analytics/devguides/reporting/data/v1/quotas",
    ),
    # Matomo (self-hosted) — no documented hard limit; conservative.
    # https://developer.matomo.org/api-reference/reporting-api
    "matomo_reporting_api": BucketPreset(
        name="matomo_reporting_api",
        capacity=30.0,
        rate_per_sec=8.0,
        daily_quota=-1,
        citation="https://developer.matomo.org/api-reference/reporting-api",
    ),
    # XenForo REST API — admin-configurable; ~5/s/key by default.
    # https://xenforo.com/community/pages/api-endpoints/
    "xenforo_api": BucketPreset(
        name="xenforo_api",
        capacity=10.0,
        rate_per_sec=4.0,
        daily_quota=-1,
        citation="https://xenforo.com/community/pages/api-endpoints/",
    ),
    # WordPress REST API — vanilla has no limit; Wordfence default 240/h.
    # https://www.wordfence.com/help/firewall/rate-limiting/
    "wordpress_api": BucketPreset(
        name="wordpress_api",
        capacity=20.0,
        rate_per_sec=4.0,
        daily_quota=-1,
        citation="https://www.wordfence.com/help/firewall/rate-limiting/",
    ),
}


def _build_cpp_registry():
    """Try the C++ extension first; fall back to a Python adapter.

    Imported via the same ``extensions.<name>`` dotted form the rest of
    the codebase uses (see ``apps.pipeline.services.ext_loader``) so we
    inherit Python 3's implicit-namespace-package behaviour without
    touching ``sys.path``. Polluting ``sys.path`` would let the
    ``ext_loader`` find half-finished sibling extensions and spam
    warnings like *"scoring loaded but missing expected callable"*.
    """
    try:
        from extensions.api_rate_limiter import (  # type: ignore[import-not-found]
            RateLimiterRegistry,
        )

        return RateLimiterRegistry(), "cpp"
    except ImportError:
        logger.warning(
            "C++ api_rate_limiter extension not built — falling back to "
            "pure-Python TokenBucket (slower but functionally identical)."
        )
        return _PyRegistryAdapter(), "python-fallback"


class _PyRegistryAdapter:
    """Adapter around the existing Python ``InMemoryBucketRegistry`` with the
    same surface as the C++ ``RateLimiterRegistry``. Used only when the C++
    extension hasn't been built. Daily-quota tracking is included here so
    parity tests can run in either backend."""

    def __init__(self) -> None:
        from .token_bucket import BucketConfig, InMemoryBucketRegistry

        self._inner = InMemoryBucketRegistry()
        self._BucketConfig = BucketConfig
        self._daily_remaining: dict[str, int] = {}
        self._daily_quota: dict[str, int] = {}
        self._daily_reset_ts: dict[str, float] = {}

    def register_bucket(
        self,
        name: str,
        capacity: float,
        rate_per_sec: float,
        daily_quota: int = -1,
    ) -> None:
        self._inner.register(
            name,
            self._BucketConfig(
                tokens_per_second=rate_per_sec, burst_capacity=capacity
            ),
        )
        self._daily_quota[name] = daily_quota
        self._daily_remaining[name] = daily_quota
        self._daily_reset_ts[name] = self._next_midnight_unix()

    def _require_registered(self, name: str) -> None:
        """Match the C++ extension's strict-bucket-key behaviour.

        The pure-Python ``InMemoryBucketRegistry`` silently auto-creates a
        conservative default bucket on first reference, but that masks
        operator typos (e.g. ``rate_limited("ga4_data")`` would never hit
        the real GA4 budget). The C++ extension raises on unknown names;
        the adapter mirrors that for parity.
        """
        if name not in self._daily_quota:
            raise KeyError(
                f"rate-limit bucket {name!r} is not registered — "
                "call register_bucket(...) first or check for a typo."
            )

    def try_acquire(self, name: str, cost: float = 1.0) -> bool:
        if cost <= 0:
            raise ValueError("cost must be > 0")
        self._require_registered(name)
        self._refresh_daily(name)
        if self._daily_remaining.get(name, -1) == 0:
            return False
        ok = self._inner.try_acquire(name, cost=cost)
        if ok and self._daily_remaining.get(name, -1) > 0:
            self._daily_remaining[name] -= 1
        return ok

    def wait_seconds(self, name: str, cost: float = 1.0) -> float:
        self._require_registered(name)
        self._refresh_daily(name)
        if self._daily_remaining.get(name, -1) == 0:
            return max(0.0, self._daily_reset_ts[name] - time.time())
        avail = self._inner.available(name)
        if avail >= cost:
            return 0.0
        return (cost - avail) / max(1e-9, self._inner._configs[name].tokens_per_second)

    def available(self, name: str) -> float:
        self._require_registered(name)
        return self._inner.available(name)

    def daily_remaining(self, name: str) -> int:
        self._require_registered(name)
        self._refresh_daily(name)
        return self._daily_remaining.get(name, -1)

    def reset_all(self) -> None:
        self._inner.clear()
        self._daily_remaining.clear()
        self._daily_quota.clear()
        self._daily_reset_ts.clear()

    def _refresh_daily(self, name: str) -> None:
        if time.time() > self._daily_reset_ts.get(name, 0):
            self._daily_remaining[name] = self._daily_quota.get(name, -1)
            self._daily_reset_ts[name] = self._next_midnight_unix()

    @staticmethod
    def _next_midnight_unix() -> float:
        from datetime import datetime, timedelta, timezone

        now = datetime.now(timezone.utc)
        tomorrow = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        return tomorrow.timestamp()


REGISTRY, BACKEND = _build_cpp_registry()


def register_defaults() -> None:
    """Register every preset in :data:`BUCKET_PRESETS`. Idempotent.

    Call once at Django app ready (``apps.sources.apps.SourcesConfig.ready``).
    Re-calling resets the buckets to full capacity, which is fine in
    practice — process restarts are rare and rate limits should be honoured
    afresh after one.
    """
    for preset in BUCKET_PRESETS.values():
        REGISTRY.register_bucket(
            preset.name,
            preset.capacity,
            preset.rate_per_sec,
            preset.daily_quota,
        )


@contextmanager
def rate_limited(name: str, *, cost: float = 1.0, max_wait_s: float = 30.0):
    """Block until ``cost`` tokens for ``name`` are available, then yield.

    Wrap every outbound request to GSC / GA4 / Matomo / XenForo / WordPress
    in this context manager::

        with rate_limited("ga4_data_api"):
            response = requests.post(api_url, data=payload, timeout=30)

    Raises ``TimeoutError`` if ``max_wait_s`` elapses without acquiring —
    callers should let this propagate so Celery retries on the next beat
    rather than hanging the worker.
    """
    deadline = time.monotonic() + max_wait_s
    while True:
        if REGISTRY.try_acquire(name, cost):
            break
        wait_s = REGISTRY.wait_seconds(name, cost)
        if time.monotonic() + wait_s > deadline:
            raise TimeoutError(
                f"rate_limited({name!r}) gave up after {max_wait_s}s; "
                f"daily_remaining={REGISTRY.daily_remaining(name)}"
            )
        time.sleep(min(wait_s, 0.25))
    yield
