"""Tests for the postgres-exporter picker (fetch -> evaluate -> file/resolve).

Uses TestCase (DB). The network fetch is patched so tests are deterministic.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import urllib.error

from django.test import TestCase, override_settings

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import pgexporter_picker


class PickPgexporterFindingsTests(TestCase):
    def _run(self, text: str) -> dict:
        with patch.object(pgexporter_picker, "_fetch_metrics_text", return_value=text):
            return pgexporter_picker.pick_pgexporter_findings()

    def test_files_an_autoissue_for_each_finding(self):
        result = self._run("pg_up 0\n")
        self.assertEqual(result["filed"], 1)
        issue = AutoIssue.objects.get(source=AutoIssue.SOURCE_PROMETHEUS)
        self.assertEqual(issue.severity, AutoIssue.SEVERITY_CRITICAL)
        self.assertEqual(issue.status, AutoIssue.STATUS_OPEN)
        self.assertIn("pg_up", issue.external_id)

    def test_rerun_is_idempotent(self):
        self._run("pg_up 0\n")
        self._run("pg_up 0\n")
        self.assertEqual(
            AutoIssue.objects.filter(
                source=AutoIssue.SOURCE_PROMETHEUS, status=AutoIssue.STATUS_OPEN
            ).count(),
            1,
        )

    def test_recovered_finding_is_resolved_with_lesson(self):
        self._run("pg_up 0\n")
        result = self._run("pg_up 1\n")
        issue = AutoIssue.objects.get(source=AutoIssue.SOURCE_PROMETHEUS)
        self.assertEqual(issue.status, AutoIssue.STATUS_RESOLVED)
        self.assertIsNotNone(issue.resolved_at)
        self.assertIn("Trap:", issue.lessons_learned)
        self.assertIn("Fix shape:", issue.lessons_learned)
        self.assertGreaterEqual(result["resolved"], 1)

    def test_healthy_metrics_file_nothing(self):
        result = self._run("pg_up 1\n")
        self.assertEqual(result["filed"], 0)
        self.assertEqual(
            AutoIssue.objects.filter(source=AutoIssue.SOURCE_PROMETHEUS).count(), 0
        )

    def test_fetch_failure_is_handled_safely(self):
        with patch.object(
            pgexporter_picker, "_fetch_metrics_text", side_effect=OSError("boom")
        ):
            result = pgexporter_picker.pick_pgexporter_findings()
        self.assertEqual(result["filed"], 0)
        self.assertEqual(result["resolved"], 0)

    @override_settings(PGEXPORTER_METRICS_URL="http://configured-exporter:9187/metrics")
    def test_default_metrics_url_comes_from_settings(self):
        seen = {}

        def fake_fetch(url):
            seen["url"] = url
            return "pg_up 1\n"

        with patch.object(pgexporter_picker, "_fetch_metrics_text", side_effect=fake_fetch):
            result = pgexporter_picker.pick_pgexporter_findings()
        self.assertEqual(seen["url"], "http://configured-exporter:9187/metrics")
        self.assertEqual(result["filed"], 0)

    def test_url_error_fetch_failure_is_handled_safely(self):
        with patch.object(
            pgexporter_picker,
            "_fetch_metrics_text",
            side_effect=urllib.error.URLError("exporter offline"),
        ):
            result = pgexporter_picker.pick_pgexporter_findings()
        self.assertEqual(result["filed"], 0)
        self.assertEqual(result["resolved"], 0)

    def test_format_findings_result_live_mode(self):
        text = pgexporter_picker.format_findings_result(
            {"filed": 2, "resolved": 1, "open": 3, "would_file": 2}, dry_run=False
        )
        self.assertNotIn("dry-run", text)
        for fragment in ("filed=2", "resolved=1", "open=3", "would_file=2"):
            self.assertIn(fragment, text)

    def test_format_findings_result_dry_run_mode(self):
        text = pgexporter_picker.format_findings_result(
            {"filed": 0, "resolved": 0, "open": 0, "would_file": 5}, dry_run=True
        )
        self.assertIn("dry-run", text)
        self.assertIn("would_file=5", text)

    def test_fetch_metrics_text_decodes_the_http_response(self):
        resp = MagicMock()
        resp.read.return_value = b"pg_up 1\n"
        cm = MagicMock()
        cm.__enter__.return_value = resp
        with patch.object(pgexporter_picker.urllib.request, "urlopen", return_value=cm):
            text = pgexporter_picker._fetch_metrics_text("http://exporter:9187/metrics")
        self.assertEqual(text, "pg_up 1\n")

    def test_dry_run_writes_nothing_but_reports_would_file(self):
        with patch.object(pgexporter_picker, "_fetch_metrics_text", return_value="pg_up 0\n"):
            result = pgexporter_picker.pick_pgexporter_findings(dry_run=True)
        self.assertEqual(result["filed"], 0)
        self.assertEqual(result["would_file"], 1)
        self.assertEqual(AutoIssue.objects.filter(source=AutoIssue.SOURCE_PROMETHEUS).count(), 0)

    def test_unrelated_open_finding_is_not_resolved(self):
        # Two findings open; next scrape clears only one — the other stays open.
        self._run("pg_up 0\npg_stat_database_deadlocks{datname=\"xf_linker\"} 2\n")
        self._run("pg_up 1\npg_stat_database_deadlocks{datname=\"xf_linker\"} 2\n")
        statuses = {
            i.external_id: i.status
            for i in AutoIssue.objects.filter(source=AutoIssue.SOURCE_PROMETHEUS)
        }
        self.assertEqual(statuses["pgexporter:pg_up_down"], AutoIssue.STATUS_RESOLVED)
        self.assertEqual(
            statuses["pgexporter:deadlocks:xf_linker"], AutoIssue.STATUS_OPEN
        )
