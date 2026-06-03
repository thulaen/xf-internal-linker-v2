from __future__ import annotations

import json
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from .models import AutoIssue


class DebugAutoIssueCommandTests(TestCase):
    def setUp(self) -> None:
        AutoIssue.objects.all().delete()

    def test_json_output_parses_when_table_is_empty(self):
        output = StringIO()
        call_command("debug_autoissue", "--json", stdout=output)

        payload = json.loads(output.getvalue())
        self.assertIn("by_source", payload)
        self.assertIn("by_status", payload)
        self.assertEqual(payload["total"], 0)

    def test_human_output_contains_stable_marker(self):
        output = StringIO()
        call_command("debug_autoissue", "--limit", "3", stdout=output)

        text = output.getvalue()
        self.assertIn("[DEBUG AUTOISSUE:", text)
        self.assertIn("AutoIssue summary", text)
