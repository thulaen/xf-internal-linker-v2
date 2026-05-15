"""Tests for async-context safety helpers."""

from __future__ import annotations

import asyncio

from django.test import SimpleTestCase, TestCase

from apps.audit.error_ingest import ingest_error
from apps.core.services.async_context import in_async_context
from apps.ops_feed.services import emit


class AsyncContextTests(SimpleTestCase):
    def test_detects_regular_sync_context(self) -> None:
        self.assertFalse(in_async_context())

    def test_detects_async_context(self) -> None:
        async def _check() -> bool:
            return in_async_context()

        self.assertTrue(asyncio.run(_check()))


class AsyncDatabaseWriteSkipTests(TestCase):
    def test_ingest_error_skips_inside_async_context(self) -> None:
        async def _call():
            return ingest_error(
                job_type="startup",
                step="async",
                error_message="startup async skip test",
            )

        self.assertIsNone(asyncio.run(_call()))

    def test_ops_feed_emit_skips_inside_async_context(self) -> None:
        async def _call() -> None:
            emit("startup.test", "Startup async skip test", source="test")

        asyncio.run(_call())
