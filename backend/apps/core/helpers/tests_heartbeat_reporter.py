"""Convention-named SimpleTestCase coverage for apps/core/helpers/heartbeat_reporter.py.

This file provides literal pinning to kill mutants and coverage for small pure 
functions in heartbeat_reporter.py. DB/Network connections are completely avoided.
"""

from __future__ import annotations

import sys
from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase

from apps.core.helpers import heartbeat_reporter


class HeartbeatReporterConstantLiteralTests(SimpleTestCase):
    def test_default_interval_secs_is_30(self) -> None:
        self.assertEqual(heartbeat_reporter.DEFAULT_INTERVAL_SECS, 30)

    def test_default_timeout_secs_is_15(self) -> None:
        self.assertEqual(heartbeat_reporter.DEFAULT_TIMEOUT_SECS, 15)

    def test_backoff_schedule_exact(self) -> None:
        self.assertEqual(
            heartbeat_reporter._BACKOFF_SCHEDULE, (30, 60, 120, 300)
        )


class ClassStopAfterGuard(Exception):
    pass


class ReadEnvTests(SimpleTestCase):
    def test_missing_env_exits(self) -> None:
        with patch.dict("os.environ", clear=True), patch("sys.exit") as mock_exit:
            mock_exit.side_effect = ClassStopAfterGuard
            with self.assertRaises(ClassStopAfterGuard):
                heartbeat_reporter._read_env()
            mock_exit.assert_called_once_with(2)


class PostHeartbeatTests(SimpleTestCase):
    def test_post_heartbeat_success(self) -> None:
        env = {
            "MAIN_PC_BASE_URL": "http://main",
            "HELPER_AUTH_TOKEN": "token123"
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = heartbeat_reporter._post_heartbeat(1, {}, env)
            self.assertTrue(result)
            mock_post.assert_called_once()
            
    def test_post_heartbeat_failure(self) -> None:
        env = {
            "MAIN_PC_BASE_URL": "http://main",
            "HELPER_AUTH_TOKEN": "token123"
        }
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        
        with patch("requests.post", return_value=mock_resp) as mock_post:
            result = heartbeat_reporter._post_heartbeat(1, {}, env)
            self.assertFalse(result)
            mock_post.assert_called_once()
