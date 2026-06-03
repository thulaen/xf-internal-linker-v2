from __future__ import annotations

from django.test import TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import vmalert_picker


def _alert(state: str = "firing"):
    return {
        "state": state,
        "labels": {
            "alertname": "ImportFailuresHigh",
            "severity": "high",
            "affected_file": "backend/apps/observability/tasks.py",
        },
        "annotations": {
            "summary": "Imports are failing",
            "description": "Import failures are above the safe threshold.",
            "trap": "Threshold alerts need stable labels for dedupe.",
            "fix_shape": "Keep alert labels stable and put details in annotations.",
        },
        "activeAt": "2026-05-21T15:00:00Z",
    }


class VmalertPickerTests(TestCase):
    def test_firing_alert_creates_vmalert_autoissue(self):
        vmalert_picker._upsert_alert(_alert())

        issue = AutoIssue.objects.get(source=AutoIssue.SOURCE_VMALERT)
        self.assertEqual(issue.title, "[vmalert] ImportFailuresHigh")
        self.assertEqual(issue.severity, AutoIssue.SEVERITY_HIGH)
        self.assertEqual(issue.affected_files, ["backend/apps/observability/tasks.py"])

    def test_refiring_alert_bumps_occurrence_count_instead_of_row_count(self):
        vmalert_picker._upsert_alert(_alert())
        vmalert_picker._upsert_alert(_alert())

        self.assertEqual(AutoIssue.objects.filter(source=AutoIssue.SOURCE_VMALERT).count(), 1)
        issue = AutoIssue.objects.get(source=AutoIssue.SOURCE_VMALERT)
        self.assertEqual(issue.occurrence_count, 2)

    def test_resolved_alert_marks_issue_resolved_with_two_part_lesson(self):
        vmalert_picker._upsert_alert(_alert())
        vmalert_picker._upsert_alert(_alert("resolved"))

        issue = AutoIssue.objects.get(source=AutoIssue.SOURCE_VMALERT)
        self.assertEqual(issue.status, AutoIssue.STATUS_RESOLVED)
        self.assertIn("Trap: Threshold alerts need stable labels for dedupe.", issue.lessons_learned)
        self.assertIn("Fix shape: Keep alert labels stable", issue.lessons_learned)

