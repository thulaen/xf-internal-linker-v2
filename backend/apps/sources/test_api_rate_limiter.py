"""FR-250 — parity tests for the C++ ``api_rate_limiter`` extension.

Compared against the pure-Python ``TokenBucket`` reference at
``backend/apps/sources/token_bucket.py``. We rely on the wrapper module to
pick the C++ extension when available and fall back to the Python adapter
otherwise — both must pass these tests.
"""

from __future__ import annotations

import time

from django.test import SimpleTestCase

from .api_rate_limiter import (
    BACKEND,
    BUCKET_PRESETS,
    REGISTRY,
    rate_limited,
    register_defaults,
)


class RateLimiterRegistryTests(SimpleTestCase):
    """Behavioural parity with ``InMemoryBucketRegistry``."""

    def setUp(self) -> None:
        REGISTRY.reset_all()
        register_defaults()

    def test_every_preset_has_a_citation(self) -> None:
        for preset in BUCKET_PRESETS.values():
            self.assertTrue(
                preset.citation.startswith("https://"),
                f"{preset.name} default lacks a source-of-truth URL",
            )

    def test_register_defaults_seeds_all_five_apis(self) -> None:
        for name in (
            "gsc_search_analytics",
            "ga4_data_api",
            "matomo_reporting_api",
            "xenforo_api",
            "wordpress_api",
        ):
            self.assertGreater(REGISTRY.available(name), 0.0)

    def test_try_acquire_decrements_tokens(self) -> None:
        REGISTRY.register_bucket("t", capacity=2.0, rate_per_sec=1.0)
        self.assertTrue(REGISTRY.try_acquire("t", 1.0))
        self.assertTrue(REGISTRY.try_acquire("t", 1.0))
        self.assertFalse(REGISTRY.try_acquire("t", 1.0))

    def test_wait_seconds_returns_deficit_over_rate(self) -> None:
        REGISTRY.register_bucket("w", capacity=1.0, rate_per_sec=2.0)
        REGISTRY.try_acquire("w", 1.0)  # drain
        # We need 1.0 token, refilling at 2/s → ~0.5s wait.
        self.assertAlmostEqual(REGISTRY.wait_seconds("w", 1.0), 0.5, delta=0.05)

    def test_refill_caps_at_capacity(self) -> None:
        REGISTRY.register_bucket("c", capacity=3.0, rate_per_sec=100.0)
        time.sleep(0.05)  # >> enough to fully refill
        self.assertAlmostEqual(REGISTRY.available("c"), 3.0, delta=0.01)

    def test_daily_quota_blocks_after_exhaustion(self) -> None:
        REGISTRY.register_bucket("d", capacity=10.0, rate_per_sec=10.0, daily_quota=2)
        self.assertTrue(REGISTRY.try_acquire("d", 1.0))
        self.assertTrue(REGISTRY.try_acquire("d", 1.0))
        self.assertFalse(REGISTRY.try_acquire("d", 1.0))  # daily quota hit
        self.assertEqual(REGISTRY.daily_remaining("d"), 0)

    def test_daily_quota_disabled_returns_minus_one(self) -> None:
        REGISTRY.register_bucket("nd", capacity=10.0, rate_per_sec=10.0)
        self.assertEqual(REGISTRY.daily_remaining("nd"), -1)

    def test_zero_or_negative_cost_raises(self) -> None:
        REGISTRY.register_bucket("z", capacity=1.0, rate_per_sec=1.0)
        with self.assertRaises((ValueError, RuntimeError)):
            REGISTRY.try_acquire("z", 0.0)

    def test_unregistered_bucket_raises(self) -> None:
        with self.assertRaises((KeyError, RuntimeError, IndexError)):
            REGISTRY.try_acquire("does-not-exist", 1.0)

    def test_rate_limited_context_manager_yields_after_acquire(self) -> None:
        REGISTRY.register_bucket("ctx", capacity=2.0, rate_per_sec=1.0)
        with rate_limited("ctx"):
            pass
        # We consumed 1 of 2 tokens; available should now be ~1.
        self.assertLess(REGISTRY.available("ctx"), 2.0)

    def test_rate_limited_times_out_when_quota_exhausted(self) -> None:
        REGISTRY.register_bucket("dt", capacity=1.0, rate_per_sec=1.0, daily_quota=1)
        with rate_limited("dt"):
            pass
        # Daily quota is now 0 → wait_seconds is hours away → timeout fast.
        with self.assertRaises(TimeoutError):
            with rate_limited("dt", max_wait_s=0.05):
                pass

    def test_rate_limited_retries_until_token_is_acquired(self) -> None:
        REGISTRY.register_bucket("retry", capacity=1.0, rate_per_sec=1000.0)
        self.assertTrue(REGISTRY.try_acquire("retry", 1.0))
        with rate_limited("retry", max_wait_s=1.0):
            pass
        self.assertLess(REGISTRY.available("retry"), 1.0)


class BackendIdentityTests(SimpleTestCase):
    """Confirm we know which backend we're running on (helps debug failures)."""

    def test_backend_is_cpp_or_python_fallback(self) -> None:
        self.assertIn(BACKEND, ("cpp", "python-fallback"))
