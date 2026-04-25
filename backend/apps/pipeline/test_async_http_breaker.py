"""Integration test for pick #3 — Circuit Breaker wiring into ``fetch_urls``.

Proof point: when a ``CircuitBreaker`` instance is passed to
``fetch_urls``,

- requests fast-fail with ``error="circuit_open"`` while the breaker
  is OPEN (no HTTP call attempted, no retry sleeps);
- successful responses call ``record_success`` so a quiet HALF_OPEN →
  CLOSED transition completes after the configured threshold;
- transient failures call ``record_failure`` so repeated bad runs
  trip CLOSED → OPEN.

The breaker's own state-machine logic is covered elsewhere; here we
only verify the wiring contract (which methods get called when, and
the fast-fail short-circuit).
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch, MagicMock

from django.test import SimpleTestCase

from apps.pipeline.services import async_http
from apps.pipeline.services.circuit_breaker import (
    CircuitBreaker,
    CircuitState,
)


def _ok_304() -> MagicMock:
    """Successful 304 response — sidesteps the body-decode path."""
    res = MagicMock()
    res.status_code = 304
    res.content = b""
    res.headers = {}
    res.text = ""
    res.encoding = ""
    return res


class _FakeAsyncClient:
    """Always returns the canned response."""

    def __init__(self, response_factory):
        self._response_factory = response_factory

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def request(self, method, url, **kw):
        return self._response_factory()


class _FailingAsyncClient:
    """Always raises the given exception class."""

    def __init__(self, exc_class):
        self._exc_class = exc_class

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return None

    async def request(self, method, url, **kw):
        raise self._exc_class("boom")


class CircuitBreakerWiringTests(SimpleTestCase):
    def _build_breaker(self) -> CircuitBreaker:
        # Aggressive thresholds so a single failure trips OPEN — keeps
        # the test deterministic without arranging multi-failure setups.
        return CircuitBreaker(
            name="test:example.com",
            failure_threshold=1,
            recovery_timeout=300,
            success_threshold=1,
            expected_exceptions=[Exception],
        )

    def test_open_breaker_short_circuits_with_circuit_open_error(self) -> None:
        """When the breaker is already OPEN, no HTTP call is made."""
        breaker = self._build_breaker()
        # Force OPEN.
        breaker.record_failure()
        self.assertTrue(breaker.is_open())

        with patch.object(async_http, "httpx") as httpx_mod:
            httpx_mod.TimeoutException = Exception
            httpx_mod.RequestError = Exception
            client = _FakeAsyncClient(lambda: _ok_304())
            httpx_mod.AsyncClient.return_value = client

            results = asyncio.run(
                async_http.fetch_urls(
                    ["https://example.invalid/a"],
                    max_concurrency=1,
                    circuit_breaker=breaker,
                )
            )

        # The fast-fail row was recorded.
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status_code"], 0)
        self.assertEqual(results[0]["error"], "circuit_open")

    def test_success_records_success_on_breaker(self) -> None:
        """Successful responses call breaker.record_success."""
        breaker = self._build_breaker()
        with patch.object(
            breaker, "record_success", wraps=breaker.record_success
        ) as record_success, patch.object(
            breaker, "record_failure", wraps=breaker.record_failure
        ) as record_failure:
            with patch.object(async_http, "httpx") as httpx_mod:
                httpx_mod.TimeoutException = Exception
                httpx_mod.RequestError = Exception
                client = _FakeAsyncClient(lambda: _ok_304())
                httpx_mod.AsyncClient.return_value = client

                asyncio.run(
                    async_http.fetch_urls(
                        ["https://example.invalid/a"],
                        max_concurrency=1,
                        circuit_breaker=breaker,
                    )
                )

        record_success.assert_called_once()
        record_failure.assert_not_called()

    def test_failure_records_failure_and_eventually_trips_open(self) -> None:
        """Repeated transient failures call record_failure each time."""
        breaker = CircuitBreaker(
            name="test:example.com",
            failure_threshold=2,
            recovery_timeout=300,
            success_threshold=1,
            expected_exceptions=[Exception],
        )
        # Three URLs; client raises on every request → three failures.
        with patch.object(
            breaker, "record_failure", wraps=breaker.record_failure
        ) as record_failure:
            with patch.object(async_http, "httpx") as httpx_mod:
                httpx_mod.TimeoutException = Exception
                httpx_mod.RequestError = Exception
                client = _FailingAsyncClient(Exception)
                httpx_mod.AsyncClient.return_value = client

                with patch("asyncio.sleep", new_callable=AsyncMock):
                    asyncio.run(
                        async_http.fetch_urls(
                            [
                                "https://example.invalid/a",
                                "https://example.invalid/b",
                                "https://example.invalid/c",
                            ],
                            max_concurrency=1,
                            max_attempts=1,  # one shot per URL → one failure each
                            circuit_breaker=breaker,
                        )
                    )

        # We expect record_failure called once per failed URL up until
        # the breaker trips. Fail #1 transitions CLOSED. Fail #2 trips
        # OPEN. Fail #3 short-circuits BEFORE reaching the HTTP path,
        # so record_failure is NOT called for that URL.
        self.assertEqual(record_failure.call_count, 2)
        # And the breaker is now OPEN.
        self.assertTrue(breaker.is_open())

    def test_no_breaker_means_no_short_circuit(self) -> None:
        """Calling fetch_urls without circuit_breaker leaves all URLs in play."""
        with patch.object(async_http, "httpx") as httpx_mod:
            httpx_mod.TimeoutException = Exception
            httpx_mod.RequestError = Exception
            client = _FakeAsyncClient(lambda: _ok_304())
            httpx_mod.AsyncClient.return_value = client

            results = asyncio.run(
                async_http.fetch_urls(
                    ["https://example.invalid/a"],
                    max_concurrency=1,
                    # circuit_breaker omitted.
                )
            )

        # Successful row, no circuit_open marker.
        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["status_code"], 304)
        self.assertNotEqual(results[0].get("error"), "circuit_open")
