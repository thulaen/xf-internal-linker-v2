from __future__ import annotations

from pathlib import Path
import subprocess
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.docker_health import (
    check_docker_health,
    file_docker_health_results,
)


def _repo_root() -> Path:
    for parent in (Path(__file__).resolve().parents):
        if (parent / "scripts" / "check-docker-health.ps1").exists():
            return parent
    repo_mount = Path("/repo")
    if (repo_mount / "scripts" / "check-docker-health.ps1").exists():
        return repo_mount
    return Path(__file__).resolve().parents[3]


REPO_ROOT = _repo_root()
DOCKER_HEALTH_SCRIPT = REPO_ROOT / "scripts" / "check-docker-health.ps1"


class DockerHealthTests(TestCase):
    def test_files_autoissue_for_windows_docker_http_500(self):
        def fake_run(command, **_kwargs):
            context = command[command.index("--context") + 1]
            if context == "desktop-linux":
                return subprocess.CompletedProcess(
                    command,
                    1,
                    "",
                    "request returned 500 Internal Server Error for API route",
                )
            return subprocess.CompletedProcess(command, 0, "ok", "")

        with patch("apps.auto_issues.services.docker_health.subprocess.run", side_effect=fake_run):
            result = check_docker_health()
            second = check_docker_health()

        self.assertEqual(result["status"], "issues-filed")
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["results"][0]["error_kind"], "http_500")
        self.assertEqual(second["autoissues"][0]["id"], result["autoissues"][0]["id"])
        self.assertEqual(
            AutoIssue.objects.filter(title__contains="Windows laptop Docker Desktop").count(),
            1,
        )

    def test_files_autoissue_for_mint_docker_errors(self):
        def fake_run(command, **_kwargs):
            context = command[command.index("--context") + 1]
            if context == "mint":
                return subprocess.CompletedProcess(
                    command,
                    1,
                    "",
                    "Cannot connect to the Docker daemon",
                )
            return subprocess.CompletedProcess(command, 0, "ok", "")

        with patch("apps.auto_issues.services.docker_health.subprocess.run", side_effect=fake_run):
            result = check_docker_health()

        self.assertEqual(result["status"], "issues-filed")
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["results"][1]["error_kind"], "daemon_unreachable")
        self.assertTrue(
            AutoIssue.objects.filter(title__contains="Mint helper Docker daemon").exists()
        )

    def test_management_command_prints_marker_without_filing_when_requested(self):
        with patch(
            "apps.auto_issues.management.commands.check_docker_health.check_docker_health",
            return_value={
                "status": "ok",
                "checked": 2,
                "failures": 0,
                "results": [],
                "autoissues": [],
            },
        ):
            call_command("check_docker_health", "--no-file")

        self.assertEqual(AutoIssue.objects.count(), 0)

    def test_precomputed_host_results_file_autoissue(self):
        result = file_docker_health_results([
            {
                "target": "windows-docker-desktop",
                "host": "Windows laptop Docker Desktop",
                "probes": [
                    {
                        "name": "ps",
                        "status": "error",
                        "command": "docker --context desktop-linux ps",
                        "expected": "Docker ps succeeds",
                        "error": "request returned 500 Internal Server Error",
                    }
                ],
            }
        ])

        self.assertEqual(result["status"], "issues-filed")
        self.assertEqual(result["failures"], 1)
        self.assertEqual(result["results"][0]["error_kind"], "http_500")
        self.assertEqual(AutoIssue.objects.count(), 1)

    def test_host_powershell_probe_applies_timeout_before_backend_call(self):
        script = DOCKER_HEALTH_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("Start-Job", script)
        self.assertIn("Wait-Job -Timeout $TimeoutSeconds", script)
        self.assertIn('status = "timeout"', script)
        self.assertIn("timed out after $TimeoutSeconds", script)
