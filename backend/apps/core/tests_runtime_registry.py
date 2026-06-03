"""Convention-named SimpleTestCase coverage for apps/core/runtime_registry.py.

This file provides literal pinning to kill mutants and coverage for small pure 
functions in runtime_registry.py. DB/Network connections are completely avoided.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core import runtime_registry


class RuntimeRegistryConstantLiteralTests(SimpleTestCase):
    # assertEqual kills the +1 mutation
    def test_embedding_dim_default_is_1024(self) -> None:
        self.assertEqual(runtime_registry._EMBEDDING_DIM_DEFAULT, 1024)

    def test_audit_log_retain_rows_is_1000(self) -> None:
        self.assertEqual(runtime_registry._AUDIT_LOG_RETAIN_ROWS, 1000)

    def test_snapshot_refresh_window_seconds_is_3600(self) -> None:
        self.assertEqual(runtime_registry._SNAPSHOT_REFRESH_WINDOW_SECONDS, 3600)

    def test_active_helper_statuses_exact(self) -> None:
        self.assertEqual(
            runtime_registry.ACTIVE_HELPER_STATUSES, {"online", "busy", "stale"}
        )

    def test_model_task_embedding_exact(self) -> None:
        self.assertEqual(runtime_registry.MODEL_TASK_EMBEDDING, "embedding")


class SafeIntSettingTests(SimpleTestCase):
    def test_safe_int_setting_empty(self) -> None:
        self.assertEqual(runtime_registry._safe_int_setting(None, 42), 42)
        self.assertEqual(runtime_registry._safe_int_setting("", 42), 42)

    def test_safe_int_setting_valid(self) -> None:
        self.assertEqual(runtime_registry._safe_int_setting("10", 42), 10)
        self.assertEqual(runtime_registry._safe_int_setting(10.5, 42), 10)

    def test_safe_int_setting_invalid(self) -> None:
        self.assertEqual(runtime_registry._safe_int_setting("abc", 42), 42)


class HelperStateTests(SimpleTestCase):
    def test_helper_state_offline(self) -> None:
        # Fast path evaluation doesn't need to patch now since status offline returns early.
        node = MagicMock()
        node.status = "offline"
        self.assertEqual(runtime_registry.helper_state(node), "offline")

    def test_helper_state_no_heartbeat(self) -> None:
        node = MagicMock()
        node.status = "online"
        node.last_heartbeat = None
        self.assertEqual(runtime_registry.helper_state(node), "offline")
