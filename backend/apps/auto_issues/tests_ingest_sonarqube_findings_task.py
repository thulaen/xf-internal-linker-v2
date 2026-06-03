"""Tests for the `auto_issues.ingest_sonarqube_findings` Celery task.

The task pairs with the `sonar-autoscan` Docker service: every 30 min Beat
fires this task, it pulls fresh SonarQube findings via REST API, and
creates / updates / merges AutoIssues. Mirrors the
`manage.py ingest_sonarqube_issues` CLI but is callable from inside the
Celery worker (no shell-out).

Test coverage:
  - Returns a skip result when SONAR_TOKEN is unset (safe no-op on fresh checkouts).
  - Returns an `unavailable` result when SonarQube cannot be reached.
  - Returns the import counts on the happy path.
  - Uses default env values when SONAR_HOST_URL / SONAR_PROJECT_KEY are unset.
"""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.auto_issues.services.sonarqube import (
    SonarImportResult,
    SonarQubeUnavailable,
)
from apps.auto_issues.tasks import ingest_sonarqube_findings


class IngestSonarqubeFindingsTaskTests(SimpleTestCase):
    def test_skips_when_token_missing(self) -> None:
        with patch.dict("os.environ", {"SONAR_TOKEN": ""}, clear=False):
            result = ingest_sonarqube_findings()
        self.assertEqual(result["status"], "skipped")
        self.assertIn("SONAR_TOKEN", result["reason"])

    def test_returns_unavailable_when_sonarqube_down(self) -> None:
        env = {
            "SONAR_TOKEN": "fake-token",
            "SONAR_HOST_URL": "http://sonarqube:9000",
            "SONAR_PROJECT_KEY": "test-key",
        }
        with patch.dict("os.environ", env, clear=False), \
                patch("apps.auto_issues.services.sonarqube.fetch_sonar_issues",
                      side_effect=SonarQubeUnavailable("HTTP 503")):
            result = ingest_sonarqube_findings()
        self.assertEqual(result["status"], "unavailable")
        self.assertIn("HTTP 503", result["reason"])

    def test_happy_path_returns_import_counts(self) -> None:
        env = {
            "SONAR_TOKEN": "fake-token",
            "SONAR_HOST_URL": "http://sonarqube:9000",
            "SONAR_PROJECT_KEY": "xf-internal-linker-v2",
        }
        fake_issues = [{"key": "AX1"}, {"key": "AX2"}]
        fake_result = SonarImportResult(created=2, updated=0, merged=0)
        with patch.dict("os.environ", env, clear=False), \
                patch("apps.auto_issues.services.sonarqube.fetch_sonar_issues",
                      return_value=fake_issues) as fetch, \
                patch("apps.auto_issues.services.sonarqube.ingest_sonarqube_issues",
                      return_value=fake_result) as ingest:
            result = ingest_sonarqube_findings()
        self.assertEqual(result["status"], "ok")
        self.assertEqual(result["total"], 2)
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(result["merged"], 0)
        fetch.assert_called_once()
        ingest.assert_called_once()

    def test_uses_default_env_when_unset(self) -> None:
        """SONAR_HOST_URL and SONAR_PROJECT_KEY have sensible defaults so a
        partially-configured machine still uses the docker-internal hostname
        and the renamed project key."""
        env = {"SONAR_TOKEN": "fake-token"}
        with patch.dict("os.environ", env, clear=True), \
                patch("apps.auto_issues.services.sonarqube.fetch_sonar_issues",
                      return_value=[]) as fetch, \
                patch("apps.auto_issues.services.sonarqube.ingest_sonarqube_issues",
                      return_value=SonarImportResult()) as ingest:
            ingest_sonarqube_findings()
        call_kwargs = fetch.call_args.kwargs
        self.assertEqual(call_kwargs["base_url"], "http://sonarqube:9000")
        self.assertEqual(call_kwargs["project_key"], "xf-internal-linker-v2")
        ingest_args, ingest_kwargs = ingest.call_args
        # _ingest(project_key, issues, base_url=...)
        self.assertEqual(ingest_args[0], "xf-internal-linker-v2")
        self.assertEqual(ingest_kwargs["base_url"], "http://sonarqube:9000")
