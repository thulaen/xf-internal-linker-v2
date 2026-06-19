"""Tests for the read-only Accuracy Lab diagnostics API."""

from __future__ import annotations

import json
import subprocess
import tempfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from rest_framework.test import APIRequestFactory, force_authenticate

from apps.diagnostics.accuracy_lab import (
    latest_report_payload,
    missing_report_payload,
    run_accuracy_audit_now,
)
from apps.diagnostics.views import (
    AccuracyFindingsView,
    AccuracyReportView,
    AccuracyRunView,
    AccuracySummaryView,
    AccuracyToolsView,
)


class AccuracyLabHelperTests(SimpleTestCase):
    def test_missing_report_returns_not_run_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            with override_settings(ACCURACY_AUDIT_DIR=temp_dir):
                payload = latest_report_payload()

        self.assertEqual(payload["status"], "not_run")
        self.assertEqual(payload["findings"], [])
        self.assertIn("matlab", payload["tools"])

    def test_missing_report_uses_configured_matlab_path_hint(self) -> None:
        matlab_path = "C:/Program Files/MATLAB/R2025b/bin/matlab.exe"
        with patch.dict("os.environ", {"XF_MATLAB_COMMAND": matlab_path}):
            payload = missing_report_payload()

        self.assertTrue(payload["tools"]["matlab"]["available"])
        self.assertEqual(payload["tools"]["matlab"]["path"], matlab_path)

    def test_corrupt_report_returns_clear_warning(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            report_path = Path(temp_dir) / "latest.json"
            report_path.write_text("{not-json", encoding="utf-8")
            with override_settings(ACCURACY_AUDIT_DIR=temp_dir):
                payload = latest_report_payload()

        self.assertEqual(payload["status"], "warning")
        self.assertEqual(payload["findings"][0]["id"], "accuracy-report-unreadable")


class AccuracyLabApiTests(SimpleTestCase):
    def setUp(self) -> None:
        self.temp_dir = tempfile.TemporaryDirectory()
        self.override = override_settings(ACCURACY_AUDIT_DIR=self.temp_dir.name)
        self.override.enable()
        self.factory = APIRequestFactory()
        self.user = SimpleNamespace(is_authenticated=True, pk=1)

    def tearDown(self) -> None:
        self.override.disable()
        self.temp_dir.cleanup()

    def test_summary_returns_not_run_before_runner_writes_report(self) -> None:
        response = self._get(AccuracySummaryView, "/api/system/status/accuracy/summary/")

        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload["status"], "not_run")
        self.assertEqual(payload["summary"]["total_findings"], 0)

    def test_tools_view_returns_matlab_payload(self) -> None:
        response = self._get(AccuracyToolsView, "/api/diagnostics/accuracy/tools/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("matlab", response.data["tools"])

    def test_summary_returns_sophisticated_check_catalog(self) -> None:
        self._write_latest_json(
            {
                "status": "warning",
                "message": "loaded",
                "sophisticated_checks": [
                    {
                        "id": "matlab_process_cleanup",
                        "name": "MATLAB process cleanup",
                        "status": "passed",
                        "message": "No leftover MATLAB process.",
                    }
                ],
            }
        )

        response = self._get(AccuracySummaryView, "/api/system/status/accuracy/summary/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            response.data["sophisticated_checks"][0]["id"],
            "matlab_process_cleanup",
        )

    def test_findings_endpoint_reads_latest_json(self) -> None:
        self._write_latest_json(
            {
                "generated_at": "2026-06-18T00:00:00+00:00",
                "status": "warning",
                "findings": [
                    {
                        "id": "matlab-unavailable",
                        "title": "MATLAB unavailable",
                        "risk": "medium",
                        "impact": "Independent numeric checks cannot run.",
                        "evidence": "matlab was not found",
                        "affected": "MATLAB",
                        "suggested_action": "Install MATLAB or add it to PATH.",
                    }
                ],
            }
        )

        response = self._get(AccuracyFindingsView, "/api/system/status/accuracy/findings/")

        self.assertEqual(response.status_code, 200)
        payload = response.data
        self.assertEqual(payload["findings"][0]["id"], "matlab-unavailable")
        self.assertEqual(payload["findings"][0]["risk"], "medium")

    def test_report_endpoint_returns_markdown_text(self) -> None:
        Path(self.temp_dir.name, "latest.md").write_text(
            "# Accuracy Lab\n\nStatus: warning\n",
            encoding="utf-8",
        )

        response = self._get(AccuracyReportView, "/api/system/status/accuracy/report/")

        self.assertEqual(response.status_code, 200)
        self.assertIn("text/markdown", response["Content-Type"])
        self.assertIn("Status: warning", response.content.decode("utf-8"))

    def test_post_is_not_allowed(self) -> None:
        request = self.factory.post("/api/system/status/accuracy/summary/", {})
        force_authenticate(request, user=self.user)
        response = AccuracySummaryView.as_view()(request)

        self.assertEqual(response.status_code, 405)

    def test_run_view_starts_read_only_runner(self) -> None:
        with patch(
            "apps.diagnostics.views.run_accuracy_audit_now",
            return_value=(200, {"status": "warning", "message": "finished", "report": {}}),
        ) as run_now:
            request = self.factory.post("/api/system/status/accuracy/run/", {})
            force_authenticate(request, user=self.user)
            response = AccuracyRunView.as_view()(request)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["status"], "warning")
        run_now.assert_called_once_with()

    def test_runner_failure_does_not_reuse_stale_passed_report(self) -> None:
        self._write_latest_json({"status": "passed", "message": "old report", "findings": []})
        failed = subprocess.CompletedProcess(["runner"], 1, "", "fresh failure")

        with patch("apps.diagnostics.accuracy_lab._run_local_runner", return_value=failed):
            status_code, payload = run_accuracy_audit_now()

        self.assertEqual(status_code, 200)
        self.assertEqual(payload["status"], "failed")
        self.assertEqual(payload["report"]["findings"][0]["id"], "accuracy-runner-failed")
        self.assertIn("fresh failure", payload["report"]["findings"][0]["evidence"])

    def _write_latest_json(self, payload: dict) -> None:
        Path(self.temp_dir.name, "latest.json").write_text(
            json.dumps(payload),
            encoding="utf-8",
        )

    def _get(self, view_class, path: str):
        request = self.factory.get(path)
        force_authenticate(request, user=self.user)
        return view_class.as_view()(request)
