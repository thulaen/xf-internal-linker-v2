"""Convention-named SimpleTestCase coverage for apps/core/views_runtime.py.

This file provides literal pinning to kill mutants and coverage for small pure 
functions in views_runtime.py. DB/Network connections are completely avoided.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core import views_runtime


class ViewsRuntimeConstantLiteralTests(SimpleTestCase):
    def test_bytes_per_megabyte_is_1048576(self) -> None:
        self.assertEqual(views_runtime._BYTES_PER_MEGABYTE, 1048576)

    def test_runtime_settings_keys_exact(self) -> None:
        self.assertEqual(
            views_runtime._RUNTIME_SETTINGS_KEYS,
            (
                "system.runtime_mode",
                "system.performance_mode",
                "system.performance_mode_expiry",
                "system.performance_mode_expires_at",
                "system.master_pause",
            ),
        )

    def test_performance_mode_choices_exact(self) -> None:
        self.assertEqual(
            views_runtime._PERFORMANCE_MODE_CHOICES, ("safe", "balanced", "high")
        )

    def test_performance_expiry_choices_exact(self) -> None:
        self.assertEqual(
            views_runtime._PERFORMANCE_EXPIRY_CHOICES, ("none", "activity", "night")
        )


class RuntimeConfigConstantLiteralTests(SimpleTestCase):
    def test_batch_size_limits_are_8_and_128(self) -> None:
        self.assertEqual(views_runtime.RuntimeConfigView.BATCH_SIZE_MIN, 8)
        self.assertEqual(views_runtime.RuntimeConfigView.BATCH_SIZE_MAX, 128)

    def test_queue_concurrency_limits_are_1_and_6(self) -> None:
        self.assertEqual(views_runtime.RuntimeConfigView.DEFAULT_QUEUE_CONCURRENCY_MIN, 1)
        self.assertEqual(views_runtime.RuntimeConfigView.DEFAULT_QUEUE_CONCURRENCY_MAX, 6)

    def test_cpu_thread_default_is_4(self) -> None:
        self.assertEqual(views_runtime.RuntimeConfigView.CPU_THREAD_DEFAULT, 4)


class ResolvePerformanceExpiryChoiceTests(SimpleTestCase):
    def test_non_high_mode_forces_none(self) -> None:
        self.assertEqual(
            views_runtime._resolve_performance_expiry_choice(mode="safe", raw_expiry="night"), 
            "none"
        )

    def test_invalid_expiry_forces_none(self) -> None:
        self.assertEqual(
            views_runtime._resolve_performance_expiry_choice(mode="high", raw_expiry="invalid"), 
            "none"
        )

    def test_valid_expiry(self) -> None:
        self.assertEqual(
            views_runtime._resolve_performance_expiry_choice(mode="high", raw_expiry="night"), 
            "night"
        )
