"""Integration test for pick #1 — Token Bucket rate limiter wiring into ``fetch_urls``.

Proof point: when ``rate_limiter_key`` is passed to ``fetch_urls``,
every fetch attempts to acquire a token from the named bucket before
issuing the HTTP call. We don't exercise the real HTTP path here —
the limiter contract is what matters, so we patch
``DEFAULT_REGISTRY.wait_and_acquire`` and assert call counts.
"""

from __future__ import annotations

import asyncio
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.pipeline.services import async_http
from apps.sources.token_bucket import (
    DEFAULT_REGISTRY as RATE_LIMITER,
    BucketConfig,
)


class TokenBucketWiringTests(SimpleTestCase):
    def setUp(self) -> None:
        # Reset state so test order doesn't matter.
        RATE_LIMITER.clear()

    def test_wait_and_acquire_called_per_url_when_key_set(self) -> None:
        """Each fetched URL invokes the bucket's wait_and_acquire exactly once."""
        # Use a generous bucket so the real wait path doesn't matter
        # — we just want to count invocations.
        RATE_LIMITER.register(
            "crawl:example.com",
            BucketConfig(tokens_per_second=1000.0, burst_capacity=1000.0),
        )

        # Patch the registry method so the test doesn't depend on
        # actual HTTP. The fetch code path will hit the
        # ``wait_and_acquire`` branch and then the real HTTP attempt
        # will fail — that's expected; we only care about the gate.
        with patch.object(RATE_LIMITER, "wait_and_acquire", return_value=True) as gate:
            asyncio.run(
                async_http.fetch_urls(
                    [
                        "https://example.invalid/a",
                        "https://example.invalid/b",
                        "https://example.invalid/c",
                    ],
                    max_concurrency=3,
                    rate_limiter_key="crawl:example.com",
                    rate_limiter_timeout=1.0,
                )
            )

        # Three URLs → three token-acquisition attempts, each on the
        # exact key the caller registered.
        self.assertEqual(gate.call_count, 3)
        for call in gate.call_args_list:
            args, kwargs = call
            # Positional first-arg is the key.
            self.assertEqual(args[0], "crawl:example.com")
            self.assertEqual(kwargs.get("cost"), 1.0)
            self.assertEqual(kwargs.get("timeout"), 1.0)

    def test_wait_and_acquire_skipped_when_no_key(self) -> None:
        """fetch_urls without rate_limiter_key never touches the bucket."""
        RATE_LIMITER.register(
            "crawl:example.com",
            BucketConfig(tokens_per_second=1000.0, burst_capacity=1000.0),
        )

        with patch.object(RATE_LIMITER, "wait_and_acquire", return_value=True) as gate:
            asyncio.run(
                async_http.fetch_urls(
                    ["https://example.invalid/a"],
                    max_concurrency=1,
                    # No rate_limiter_key.
                )
            )

        self.assertEqual(gate.call_count, 0)

    def test_timeout_records_rate_limited_error(self) -> None:
        """When wait_and_acquire returns False (timeout), the row is rate_limited."""
        RATE_LIMITER.register(
            "crawl:example.com",
            BucketConfig(tokens_per_second=1.0, burst_capacity=1.0),
        )

        # Force every acquisition to fail.
        with patch.object(RATE_LIMITER, "wait_and_acquire", return_value=False):
            results = asyncio.run(
                async_http.fetch_urls(
                    ["https://example.invalid/a"],
                    max_concurrency=1,
                    rate_limiter_key="crawl:example.com",
                    rate_limiter_timeout=0.1,
                )
            )

        # Wait failed → the request was never issued, so the result
        # row carries the explicit ``rate_limited`` error code that
        # operators can grep for in production logs.
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["url"], "https://example.invalid/a")
        self.assertEqual(results[0]["status_code"], 0)
        self.assertEqual(results[0]["error"], "rate_limited")
        self.assertEqual(results[0]["content"], "")
