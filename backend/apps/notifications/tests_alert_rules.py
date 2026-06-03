"""Convention-named SimpleTestCase coverage for apps/notifications/alert_rules.py.

This commit only reworded the docstring/comment of ``alert_gpu_fallback_to_cpu``
(and the module header) from GPU-fallback wording to paid-embedding-provider
wording — no executable code changed.  This test imports the module and calls
the function with ``emit_operator_alert`` mocked so the function body runs
without a database, which lets the diff-coverage gate measure the file.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from django.test import SimpleTestCase


class AlertGpuFallbackToCpuTests(SimpleTestCase):
    def test_emits_operator_alert_with_reason(self) -> None:
        from apps.notifications import alert_rules

        sentinel = object()
        with patch.object(
            alert_rules, "emit_operator_alert", return_value=sentinel
        ) as mock_emit:
            result = alert_rules.alert_gpu_fallback_to_cpu(
                reason="provider unavailable"
            )

        self.assertIs(result, sentinel)
        mock_emit.assert_called_once()
        kwargs = mock_emit.call_args.kwargs
        self.assertIn("provider unavailable", kwargs["message"])
