from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.test import SimpleTestCase

from apps.auto_issues import tasks
from config.settings.celery_schedules import CELERY_BEAT_SCHEDULE


class RegistryRefreshTests(SimpleTestCase):
    def test_registry_read_refresh_runs_print_open_issues(self):
        with patch("django.core.management.call_command") as call_command:
            call_command.side_effect = lambda *_, stdout=None, **__: stdout.write(
                "[REGISTRY READ: 0 open auto-issues]\n"
            )

            result = tasks.refresh_registry_read()

        call_command.assert_called_once()
        self.assertEqual(call_command.call_args.args, ("print_open_issues",))
        self.assertIsInstance(call_command.call_args.kwargs["stdout"], StringIO)
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["line_count"], 1)

    def test_registry_read_refresh_is_scheduled_every_thirty_minutes(self):
        entry = CELERY_BEAT_SCHEDULE["auto-issues-registry-read-refresh"]

        self.assertEqual(entry["task"], "auto_issues.refresh_registry_read")
        self.assertEqual(entry["schedule"], 1800.0)
        self.assertEqual(entry["options"]["expires"], 1700)
