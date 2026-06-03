"""Tests for importing SonarQube findings into AutoIssues."""

from __future__ import annotations

from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.sonarqube import (
    SonarQubeUnavailable,
    ingest_sonarqube_issues,
    map_sonar_severity,
    sonar_file_path,
)


class SonarQubeImportTests(TestCase):
    def test_fake_sonarqube_issue_creates_autoissue(self) -> None:
        issue = _sonar_issue(key="AX1", file_path="backend/apps/core/models.py")

        created = ingest_sonarqube_issues("xf-linker", [issue])

        self.assertEqual(created.created, 1)
        row = AutoIssue.objects.get(external_id="sonarqube:xf-linker:AX1")
        self.assertEqual(row.source, AutoIssue.SOURCE_SONARQUBE)
        self.assertEqual(row.affected_files, ["backend/apps/core/models.py"])
        self.assertIn("Example message", row.description)

    def test_reimport_updates_existing_autoissue_without_duplicate(self) -> None:
        issue = _sonar_issue(key="AX1", file_path="backend/apps/core/models.py")

        first = ingest_sonarqube_issues("xf-linker", [issue])
        second = ingest_sonarqube_issues("xf-linker", [issue])

        self.assertEqual(first.created, 1)
        self.assertEqual(second.updated, 1)
        rows = AutoIssue.objects.filter(external_id="sonarqube:xf-linker:AX1")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.get().occurrence_count, 1)

    def test_same_rule_and_file_on_different_lines_stays_separate(self) -> None:
        issues = [
            _sonar_issue(key="AX-line-17", file_path="backend/apps/core/models.py", line=17),
            _sonar_issue(key="AX-line-41", file_path="backend/apps/core/models.py", line=41),
        ]

        result = ingest_sonarqube_issues("xf-linker", issues)

        self.assertEqual(result.created, 2)
        self.assertEqual(
            AutoIssue.objects.filter(external_id__startswith="sonarqube:xf-linker:AX-line-").count(),
            2,
        )

    def test_same_rule_file_line_and_message_can_merge_across_key_churn(self) -> None:
        issues = [
            _sonar_issue(key="AX-old-key", file_path="backend/apps/core/views.py", line=88),
            _sonar_issue(key="AX-new-key", file_path="backend/apps/core/views.py", line=88),
        ]

        result = ingest_sonarqube_issues("xf-linker", issues)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.merged, 1)
        row = AutoIssue.objects.get(external_id="sonarqube:xf-linker:AX-old-key")
        self.assertEqual(row.occurrence_count, 2)
        self.assertEqual(len(row.source_observations), 2)

    def test_reopened_sonarqube_key_reuses_resolved_row(self) -> None:
        issue = _sonar_issue(key="AX-reopened", file_path="backend/apps/core/jobs.py", line=12)
        AutoIssue.objects.create(
            source=AutoIssue.SOURCE_SONARQUBE,
            external_id="sonarqube:xf-linker:AX-reopened",
            fingerprint="old-fingerprint",
            canonical_fingerprint="old-fingerprint",
            title="old resolved issue",
            description="old",
            affected_files=["backend/apps/core/jobs.py"],
            status=AutoIssue.STATUS_RESOLVED,
            severity=AutoIssue.SEVERITY_LOW,
            priority_score=0.1,
            lessons_learned="Trap: SonarQube keys can reappear. Fix shape: reuse the row safely.",
        )

        result = ingest_sonarqube_issues("xf-linker", [issue])

        self.assertEqual(result.updated, 1)
        rows = AutoIssue.objects.filter(external_id="sonarqube:xf-linker:AX-reopened")
        self.assertEqual(rows.count(), 1)
        row = rows.get()
        self.assertEqual(row.status, AutoIssue.STATUS_OPEN)
        self.assertEqual(row.title, "[sonarqube] python:S1234: backend/apps/core/jobs.py")

    def test_severity_mapping_uses_sonarqube_levels(self) -> None:
        self.assertEqual(map_sonar_severity("BLOCKER"), AutoIssue.SEVERITY_CRITICAL)
        self.assertEqual(map_sonar_severity("CRITICAL"), AutoIssue.SEVERITY_HIGH)
        self.assertEqual(map_sonar_severity("MAJOR"), AutoIssue.SEVERITY_MEDIUM)
        self.assertEqual(map_sonar_severity("MINOR"), AutoIssue.SEVERITY_LOW)
        self.assertEqual(map_sonar_severity("INFO"), AutoIssue.SEVERITY_LOW)
        self.assertEqual(map_sonar_severity("UNKNOWN"), AutoIssue.SEVERITY_LOW)

    def test_component_key_becomes_repo_relative_path(self) -> None:
        issue = _sonar_issue(key="AX2", file_path="frontend/src/app/app.component.ts")

        self.assertEqual(
            sonar_file_path(issue, "xf-linker"),
            "frontend/src/app/app.component.ts",
        )

    @patch("apps.auto_issues.management.commands.ingest_sonarqube_issues.fetch_sonar_issues")
    def test_command_reports_offline_sonarqube_without_crashing(self, fetch_mock) -> None:
        fetch_mock.side_effect = SonarQubeUnavailable("connection refused")
        out = StringIO()

        call_command("ingest_sonarqube_issues", "--project-key", "xf-linker", stdout=out)

        self.assertIn("SONARQUBE UNAVAILABLE: connection refused", out.getvalue())


def _sonar_issue(*, key: str, file_path: str, line: int = 17) -> dict:
    return {
        "key": key,
        "rule": "python:S1234",
        "component": f"xf-linker:{file_path}",
        "message": "Example message",
        "severity": "MAJOR",
        "type": "BUG",
        "line": line,
    }
