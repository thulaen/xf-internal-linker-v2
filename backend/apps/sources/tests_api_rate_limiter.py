"""Convention-named discovery shim for apps/sources/api_rate_limiter.py.

The mutation gate only discovers a file named ``tests_<stem>.py`` in the same
directory as ``<stem>.py``. The proven coverage for ``api_rate_limiter.py`` lives
in the differently-prefixed ``test_api_rate_limiter.py`` next to this file. To
avoid duplicating ~100 lines of asserted behaviour (which would drift), this shim
re-exports those test classes under the discoverable name so the same assertions
run when the gate collects ``tests_api_rate_limiter.py``.

All re-exported tests are ``SimpleTestCase`` and use the in-memory token-bucket
registry only — no database, network, or filesystem — so this is hang-safe for
the mutation gate.
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.sources.api_rate_limiter import REGISTRY, rate_limited, register_defaults
from apps.sources.test_api_rate_limiter import (  # noqa: F401
    BackendIdentityTests,
    RateLimiterRegistryTests,
)

__all__ = [
    "BackendIdentityTests",
    "RateLimiterRegistryTests",
    "RateLimitedAcquireLoopTests",
]


class RateLimitedAcquireLoopTests(SimpleTestCase):
    """Pin the ``acquired`` loop-flag refactor in ``rate_limited``.

    The loop was rewritten from ``while True: ... break`` to a boolean flag
    (``acquired = False`` / ``while not acquired`` / ``acquired = True``).
    These tests kill the changed-line mutants: ``acquired = False`` -> ``True``
    (loop never runs, never acquires) and ``not acquired`` negation.
    """

    def setUp(self) -> None:
        REGISTRY.reset_all()
        register_defaults()

    def test_acquires_on_first_pass_consuming_one_token(self) -> None:
        REGISTRY.register_bucket("first", capacity=2.0, rate_per_sec=1.0)
        with rate_limited("first"):
            pass
        # Exactly one token consumed: 2.0 - 1.0 = ~1.0. If the loop never ran
        # (mutant flipping the flag) no token is consumed and available stays 2.0.
        self.assertAlmostEqual(REGISTRY.available("first"), 1.0, delta=0.05)

    def test_loops_until_token_refills_then_acquires(self) -> None:
        # Drain the bucket so the first try_acquire inside rate_limited fails and
        # the loop body must run again after a refill. A fast refill rate keeps
        # the wait short. The post-condition proves a token was actually consumed
        # by the loop, which a flag-flip or negation mutant (loop never runs)
        # cannot satisfy.
        REGISTRY.register_bucket("multi", capacity=1.0, rate_per_sec=1000.0)
        self.assertTrue(REGISTRY.try_acquire("multi", 1.0))  # drain to empty
        with rate_limited("multi", max_wait_s=1.0):
            pass
        # A token was acquired after the refill: available is below the 1.0
        # capacity. If the loop never ran, no acquire happened and the bucket
        # would refill back toward capacity instead.
        self.assertLess(REGISTRY.available("multi"), 1.0)
