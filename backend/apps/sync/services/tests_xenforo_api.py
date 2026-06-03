"""Convention-named SimpleTestCase coverage for sync/services/xenforo_api.py.

The exhausted-retries log line was lowered from ``logger.error`` to
``logger.warning`` because a XenForo request that fails after all retries is a
recoverable, expected transient condition, not an application error.  This test
drives the retry loop to exhaustion with a mocked ``requests.get`` and asserts
the final log call is a WARNING and the original exception is re-raised, which
also exercises the changed log line.
"""

from __future__ import annotations

import time
from unittest.mock import patch

import requests
from django.test import SimpleTestCase

from apps.sync.services.xenforo_api import XenForoAPIClient


class XenForoExhaustedRetriesLogLevelTests(SimpleTestCase):
    def test_logs_warning_and_reraises_after_retries(self) -> None:
        client = XenForoAPIClient(base_url="https://forum.example.com", api_key="k")

        with patch(
            "apps.sync.services.xenforo_api.requests.get",
            side_effect=requests.exceptions.ConnectionError("down"),
        ), patch.object(time, "sleep"), patch(
            "apps.sync.services.xenforo_api.rate_limited"
        ), patch(
            "apps.sync.services.xenforo_api.logger.warning"
        ) as mock_warning, patch(
            "apps.sync.services.xenforo_api.logger.error"
        ) as mock_error:
            with self.assertRaises(requests.exceptions.ConnectionError):
                client._get("threads/")

        # Three attempts: two retry warnings + one final exhausted warning.
        self.assertEqual(mock_warning.call_count, 3)
        # The exhausted-retries line was lowered from error to warning: assert
        # logger.error is never called so a mutant flipping warning->error on
        # the changed line is killed.
        self.assertEqual(mock_error.call_count, 0)
        # Exact format string of the final (exhausted) warning — pins the string
        # literal so a substring/identifier mutant on it is killed.
        self.assertEqual(
            mock_warning.call_args_list[-1].args[0],
            "XenForo API request failed after %d attempts: %s (URL: %s)",
        )
