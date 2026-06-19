"""Tests for the local Accuracy Lab runner."""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import run_accuracy_audit as audit  # noqa: E402


class AccuracyAuditRunnerTests(unittest.TestCase):
    def test_build_report_marks_missing_matlab_as_warning(self) -> None:
        with patch("run_accuracy_audit._discover_matlab_command", return_value=None):
            with patch("run_accuracy_audit.shutil.which", return_value=None):
                report = audit.build_report(
                    matlab_command=None,
                    rust_command=None,
                    skip_matlab=False,
                )

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["findings"][0]["id"], "matlab-unavailable")
        self.assertEqual(report["tools"]["matlab"]["status"], "missing")

    def test_fake_matlab_success_passes_numeric_precision(self) -> None:
        completed = Mock(
            returncode=0,
            stdout="\n".join(
                [
                    "ACCURACY_LAB_MATLAB_OK",
                    "ACCURACY_LAB_RELEASE=2025b",
                    "ACCURACY_LAB_JAVA=1.8.0_202",
                    "ACCURACY_LAB_DESKTOP=false",
                    "ACCURACY_LAB_SCORE=0.7235",
                    "ACCURACY_LAB_THREAD_CAP=6",
                    "ACCURACY_LAB_CORE_COUNT=12",
                ]
            ),
            stderr="",
        )
        with patch("run_accuracy_audit._process_ids", return_value=set()):
            with patch("run_accuracy_audit.subprocess.run", return_value=completed) as run:
                report = audit.build_report(
                    matlab_command="fake-matlab",
                    rust_command=None,
                    skip_matlab=False,
                )

        command = run.call_args.args[0]
        self.assertNotIn("-singleCompThread", command)
        self.assertIn("-noFigureWindows", command)
        self.assertEqual(report["resource_safety"]["thread_policy"]["min_cores"], 4)
        self.assertEqual(report["resource_safety"]["thread_policy"]["max_threads"], 6)
        self.assertEqual(report["resource_safety"]["thread_policy"]["thread_cap"], 6)
        self.assertEqual(report["resource_safety"]["thread_policy"]["status"], "passed")
        self.assertEqual(report["resource_safety"]["cleanup_status"], "clean")
        self.assertEqual(len(report["sophisticated_checks"]), 56)
        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["tools"]["matlab"]["version"], "R2025b")
        self.assertEqual(report["checks"][1]["status"], "passed")
        self.assertEqual(report["checks"][2]["status"], "not_run")

    def test_matlab_leftover_process_is_high_risk_finding(self) -> None:
        completed = Mock(
            returncode=0,
            stdout="\n".join(
                [
                    "ACCURACY_LAB_MATLAB_OK",
                    "ACCURACY_LAB_RELEASE=2025b",
                    "ACCURACY_LAB_JAVA=1.8.0_202",
                    "ACCURACY_LAB_DESKTOP=false",
                    "ACCURACY_LAB_SCORE=0.7235",
                    "ACCURACY_LAB_THREAD_CAP=6",
                    "ACCURACY_LAB_CORE_COUNT=12",
                ]
            ),
            stderr="",
        )
        with patch("run_accuracy_audit._process_ids", side_effect=[set(), {4321}]):
            with patch("run_accuracy_audit.subprocess.run", return_value=completed):
                report = audit.build_report(
                    matlab_command="fake-matlab",
                    rust_command=None,
                    skip_matlab=False,
                )

        self.assertEqual(report["tools"]["matlab"]["cleanup_status"], "leftover")
        self.assertEqual(report["findings"][0]["risk"], "high")
        self.assertEqual(report["resource_safety"]["lingering_pids"], [4321])

    def test_matlab_toolbox_license_and_path_inventory_are_reported(self) -> None:
        completed = Mock(
            returncode=0,
            stdout="\n".join(
                [
                    "ACCURACY_LAB_MATLAB_OK",
                    "ACCURACY_LAB_RELEASE=2025b",
                    "ACCURACY_LAB_JAVA=1.8.0_202",
                    "ACCURACY_LAB_DESKTOP=false",
                    "ACCURACY_LAB_SCORE=0.7235",
                    "ACCURACY_LAB_THREAD_CAP=6",
                    "ACCURACY_LAB_CORE_COUNT=12",
                    "ACCURACY_LAB_TOOLBOX=Statistics and Machine Learning Toolbox",
                    "ACCURACY_LAB_LICENSE_statistics=1",
                    "ACCURACY_LAB_WHICH_sum=built-in",
                ]
            ),
            stderr="",
        )
        with patch("run_accuracy_audit._process_ids", return_value=set()):
            with patch("run_accuracy_audit.subprocess.run", return_value=completed):
                report = audit.build_report(
                    matlab_command="fake-matlab",
                    rust_command=None,
                    skip_matlab=False,
                )

        matlab = report["tools"]["matlab"]
        self.assertIn("Statistics and Machine Learning Toolbox", matlab["toolboxes"])
        self.assertTrue(matlab["licenses"]["statistics"])
        self.assertEqual(matlab["path_hygiene"]["sum"], "built-in")

    def test_missing_matlab_score_is_reported_as_warning(self) -> None:
        completed = Mock(
            returncode=0,
            stdout="\n".join(
                [
                    "ACCURACY_LAB_MATLAB_OK",
                    "ACCURACY_LAB_RELEASE=2025b",
                    "ACCURACY_LAB_JAVA=1.8.0_202",
                    "ACCURACY_LAB_DESKTOP=false",
                ]
            ),
            stderr="",
        )
        with patch("run_accuracy_audit._process_ids", return_value=set()):
            with patch("run_accuracy_audit.subprocess.run", return_value=completed):
                report = audit.build_report(
                    matlab_command="fake-matlab",
                    rust_command=None,
                    skip_matlab=False,
                )

        self.assertEqual(report["status"], "warning")
        self.assertEqual(report["tools"]["matlab"]["status"], "failed")
        self.assertEqual(report["checks"][1]["status"], "not_run")

    def test_write_reports_creates_json_and_markdown(self) -> None:
        report = audit.build_report(
            matlab_command=None,
            rust_command=None,
            skip_matlab=True,
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            audit.write_reports(report, Path(temp_dir))
            json_path = Path(temp_dir) / "latest.json"
            markdown_path = Path(temp_dir) / "latest.md"

            saved = json.loads(json_path.read_text(encoding="utf-8"))
            markdown = markdown_path.read_text(encoding="utf-8")

        self.assertEqual(saved["status"], report["status"])
        self.assertIn("# Accuracy Lab", markdown)

    def test_markdown_includes_agent_ready_finding_fields(self) -> None:
        with patch("run_accuracy_audit._discover_matlab_command", return_value=None):
            with patch("run_accuracy_audit.shutil.which", return_value=None):
                report = audit.build_report(
                    matlab_command=None,
                    rust_command=None,
                    skip_matlab=False,
                )
        markdown = audit._markdown_report(report)  # pylint: disable=protected-access

        self.assertIn("Impact:", markdown)
        self.assertIn("Affected:", markdown)
        self.assertIn("Suggested action:", markdown)


if __name__ == "__main__":
    unittest.main()
