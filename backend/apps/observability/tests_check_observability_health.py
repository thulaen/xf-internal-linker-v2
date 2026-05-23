"""Regression tests for ``manage.py check_observability_health`` (Phase K.4).

Covers four shapes:

1. All 15 services healthy -> marker emits ``status=healthy
   failing_signals=none`` and no AutoIssue is filed.
2. Single service degraded -> marker emits ``status=degraded`` naming
   the service; a single AutoIssue is filed with the deduping
   canonical_fingerprint shape ``observability:<svc>:<state>:<health>``.
3. Multi-service degraded (mixed absent / restarting / exited) -> all
   are listed and all are filed.
4. Repeat invocation against the same failure shape -> dedup bumps
   ``occurrence_count`` instead of creating a second row.
"""
from __future__ import annotations

import json
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import TestCase

from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.observability.management.commands.check_observability_health import (
    OBSERVABILITY_SERVICES,
)


def _row(service: str, state: str = "running", health: str = "healthy") -> dict:
    return {"Service": service, "State": state, "Health": health}


def _healthy_rows() -> list[dict]:
    return [_row(name) for name in OBSERVABILITY_SERVICES]


class HappyPathTests(TestCase):
    def test_all_healthy_emits_clean_marker(self) -> None:
        out = StringIO()
        with patch(
            "apps.observability.management.commands.check_observability_health._docker_compose_ps_json",
            return_value=_healthy_rows(),
        ):
            call_command("check_observability_health", stdout=out)
        output = out.getvalue()
        self.assertIn("[OBSERVABILITY HEALTH: status=healthy", output)
        self.assertIn("failing_signals=none", output)
        self.assertEqual(AutoIssue.objects.count(), 0)

    def test_starting_health_treated_as_ok(self) -> None:
        rows = _healthy_rows()
        rows[0]["Health"] = "starting"
        out = StringIO()
        with patch(
            "apps.observability.management.commands.check_observability_health._docker_compose_ps_json",
            return_value=rows,
        ):
            call_command("check_observability_health", stdout=out)
        self.assertIn("status=healthy", out.getvalue())
        self.assertEqual(AutoIssue.objects.count(), 0)


class SingleFailureTests(TestCase):
    def test_absent_service_files_autoissue(self) -> None:
        rows = [r for r in _healthy_rows() if r["Service"] != "sonarqube"]
        out = StringIO()
        with patch(
            "apps.observability.management.commands.check_observability_health._docker_compose_ps_json",
            return_value=rows,
        ):
            call_command("check_observability_health", stdout=out)
        output = out.getvalue()
        self.assertIn("status=degraded", output)
        self.assertIn("sonarqube", output)
        autoissues = AutoIssue.objects.filter(
            canonical_fingerprint__startswith="observability:sonarqube:absent"
        )
        self.assertEqual(autoissues.count(), 1)
        self.assertEqual(autoissues.first().severity, AutoIssue.SEVERITY_HIGH)

    def test_unhealthy_state_files_autoissue(self) -> None:
        rows = _healthy_rows()
        for row in rows:
            if row["Service"] == "loki":
                row["State"] = "restarting"
                row["Health"] = "unhealthy"
        out = StringIO()
        with patch(
            "apps.observability.management.commands.check_observability_health._docker_compose_ps_json",
            return_value=rows,
        ):
            call_command("check_observability_health", stdout=out)
        self.assertIn("loki", out.getvalue())
        self.assertEqual(
            AutoIssue.objects.filter(
                canonical_fingerprint="observability:loki:restarting:unhealthy"
            ).count(),
            1,
        )


class MultiFailureTests(TestCase):
    def test_multiple_failures_listed_and_filed(self) -> None:
        rows = _healthy_rows()
        for row in rows:
            if row["Service"] in {"loki", "tempo", "grafana"}:
                row["State"] = "exited"
                row["Health"] = ""
        out = StringIO()
        with patch(
            "apps.observability.management.commands.check_observability_health._docker_compose_ps_json",
            return_value=rows,
        ):
            call_command("check_observability_health", stdout=out)
        output = out.getvalue()
        self.assertIn("loki", output)
        self.assertIn("tempo", output)
        self.assertIn("grafana", output)
        self.assertEqual(
            AutoIssue.objects.filter(
                canonical_fingerprint__startswith="observability:loki:exited",
            ).count(),
            1,
        )
        self.assertEqual(
            AutoIssue.objects.filter(
                canonical_fingerprint__startswith="observability:tempo:exited",
            ).count(),
            1,
        )


class DedupTests(TestCase):
    def test_repeat_invocation_bumps_occurrence_count(self) -> None:
        rows = [r for r in _healthy_rows() if r["Service"] != "pyroscope"]
        with patch(
            "apps.observability.management.commands.check_observability_health._docker_compose_ps_json",
            return_value=rows,
        ):
            call_command("check_observability_health", stdout=StringIO())
            call_command("check_observability_health", stdout=StringIO())
            call_command("check_observability_health", stdout=StringIO())
        autoissues = AutoIssue.objects.filter(
            canonical_fingerprint__startswith="observability:pyroscope:absent"
        )
        self.assertEqual(autoissues.count(), 1)
        self.assertEqual(autoissues.first().occurrence_count, 3)


class DryRunTests(TestCase):
    def test_dry_run_does_not_file(self) -> None:
        rows = [r for r in _healthy_rows() if r["Service"] != "vmsingle"]
        out = StringIO()
        with patch(
            "apps.observability.management.commands.check_observability_health._docker_compose_ps_json",
            return_value=rows,
        ):
            call_command("check_observability_health", "--dry-run", stdout=out)
        self.assertIn("status=degraded", out.getvalue())
        self.assertEqual(AutoIssue.objects.count(), 0)
