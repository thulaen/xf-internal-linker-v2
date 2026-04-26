"""Integration test for pick #2 — AWS full-jitter exponential backoff wiring into ``fetch_urls``.

Proof point: when ``max_attempts > 1``, transient HTTP errors
(``httpx.TimeoutException``, ``httpx.RequestError``) trigger a retry
with ``apps.sources.backoff.full_jitter_delay``-driven sleeps between
attempts. After ``max_attempts`` failures the final error row is
recorded and the URL is given up on. ``max_attempts == 1`` (the
default) preserves single-shot behaviour.

We patch ``asyncio.sleep`` and ``full_jitter_delay`` so the tests are
deterministic and don't actually wait. The HTTP path itself is
patched to fail a controllable number of times — that's all we need
to prove the wiring contract.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from django.test import SimpleTestCase

from apps.pipeline.services import async_http


def _ok_response() -> MagicMock:
    """Build a successful ``httpx.Response``-shaped mock.

    Status 304 sidesteps the body-decode path (which calls into
    ``apps.sources.encoding``) so these tests stay focused on the
    retry loop itself, not the body-handling tangent.
    """
    res = MagicMock()
    res.status_code = 304
    res.content = b""
    res.headers = {}
    res.text = ""
    res.encoding = ""
    return res


class _FlakyClient:
    """Async-context-manager that fails the first N requests, then succeeds.

    We track per-URL call counts so each URL exhibits its own retry
    sequence — important for tests that exercise multiple URLs
    concurrently.
    """

    def __init__(self, fail_first_n: int, exception_class):
        self.fail_first_n = fail_first_n
        self.exception_class = exception_class
        self.calls_per_url: dict[str, int] = {}

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def request(self, method, url, **kw):
        n = self.calls_per_url.get(url, 0)
        self.calls_per_url[url] = n + 1
        if n < self.fail_first_n:
            raise self.exception_class("simulated transient error")
        return _ok_response()


class BackoffWiringTests(SimpleTestCase):
    def test_max_attempts_one_means_no_retry(self) -> None:
        """``max_attempts=1`` is the pre-pick-2 single-shot behaviour."""
        # Build a mock httpx that raises a TimeoutException on every call.
        with patch.object(async_http, "httpx") as httpx_mod:
            httpx_mod.TimeoutException = Exception
            httpx_mod.RequestError = Exception
            client = _FlakyClient(fail_first_n=99, exception_class=Exception)
            httpx_mod.AsyncClient.return_value = client

            with patch("asyncio.sleep", new_callable=AsyncMock) as sleep:
                results = asyncio.run(
                    async_http.fetch_urls(
                        ["https://example.invalid/a"],
                        max_concurrency=1,
                        max_attempts=1,
                    )
                )

        # Exactly one HTTP attempt, no sleep called.
        self.assertEqual(client.calls_per_url["https://example.invalid/a"], 1)
        sleep.assert_not_called()
        # And the result row records the failure.
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status_code"], 0)

    def test_retries_until_success(self) -> None:
        """Two failures then success → 3rd attempt succeeds, 2 sleeps."""
        with patch.object(async_http, "httpx") as httpx_mod:
            httpx_mod.TimeoutException = Exception
            httpx_mod.RequestError = Exception
            client = _FlakyClient(fail_first_n=2, exception_class=Exception)
            httpx_mod.AsyncClient.return_value = client

            with (
                patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
                patch(
                    "apps.sources.backoff.full_jitter_delay", return_value=0.0
                ) as delay,
            ):
                results = asyncio.run(
                    async_http.fetch_urls(
                        ["https://example.invalid/a"],
                        max_concurrency=1,
                        max_attempts=5,
                        backoff_base=0.1,
                        backoff_cap=2.0,
                    )
                )

        # 3 HTTP attempts (2 failed, 1 succeeded).
        self.assertEqual(client.calls_per_url["https://example.invalid/a"], 3)
        # 2 sleeps between the 3 attempts.
        self.assertEqual(sleep.call_count, 2)
        # Both delays computed from full_jitter_delay with the right knobs.
        self.assertEqual(delay.call_count, 2)
        for call in delay.call_args_list:
            args, kwargs = call
            self.assertEqual(kwargs.get("base"), 0.1)
            self.assertEqual(kwargs.get("cap"), 2.0)
        # Result row reports the eventual success (304 unchanged path).
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status_code"], 304)

    def test_all_attempts_fail_records_last_error(self) -> None:
        """All max_attempts fail → result row carries the final error."""
        with patch.object(async_http, "httpx") as httpx_mod:
            httpx_mod.TimeoutException = Exception
            httpx_mod.RequestError = Exception
            client = _FlakyClient(fail_first_n=99, exception_class=Exception)
            httpx_mod.AsyncClient.return_value = client

            with (
                patch("asyncio.sleep", new_callable=AsyncMock) as sleep,
                patch("apps.sources.backoff.full_jitter_delay", return_value=0.0),
            ):
                results = asyncio.run(
                    async_http.fetch_urls(
                        ["https://example.invalid/a"],
                        max_concurrency=1,
                        max_attempts=3,
                    )
                )

        # 3 HTTP attempts, 2 sleeps between them.
        self.assertEqual(client.calls_per_url["https://example.invalid/a"], 3)
        self.assertEqual(sleep.call_count, 2)
        # Final error row recorded.
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status_code"], 0)
        # The exception class lookup ``httpx.TimeoutException`` was
        # aliased to ``Exception`` for the mock, so every raised
        # exception is classified as a timeout — recorded message is
        # the literal string the production code uses, not the
        # exception's str().
        self.assertEqual(results[0]["error"], "timeout")
