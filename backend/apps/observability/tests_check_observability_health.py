"""Regression tests for ``manage.py check_observability_health`` (Phase K.4).

Covers four shapes:

1. All local services healthy -> marker emits ``status=healthy
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


def _row(service: str, state: str = "Running", health: str = "Ready") -> dict:
    return {"Service": service, "State": state, "Health": health}


def _healthy_rows() -> list[dict]:
    return [_row(name) for name in OBSERVABILITY_SERVICES]


def _patch_service_state(rows: list[dict]):
    states = {row["Service"]: (row["State"], row["Health"]) for row in rows}

    def fake_state(service: str) -> tuple[str, str]:
        return states.get(service, ("absent", ""))

    return patch(
        "apps.observability.management.commands.check_observability_health._service_state",
        side_effect=fake_state,
    )


class HappyPathTests(TestCase):
    def test_all_healthy_emits_clean_marker(self) -> None:
        before = AutoIssue.objects.count()
        out = StringIO()
        with _patch_service_state(_healthy_rows()):
            call_command("check_observability_health", stdout=out)
        output = out.getvalue()
        self.assertIn("[OBSERVABILITY HEALTH: status=healthy", output)
        self.assertIn("failing_signals=none", output)
        self.assertEqual(AutoIssue.objects.count(), before)

    def test_starting_health_treated_as_ok(self) -> None:
        before = AutoIssue.objects.count()
        rows = _healthy_rows()
        rows[0]["Health"] = "Ready"
        out = StringIO()
        with _patch_service_state(rows):
            call_command("check_observability_health", stdout=out)
        self.assertIn("status=healthy", out.getvalue())
        self.assertEqual(AutoIssue.objects.count(), before)


class SingleFailureTests(TestCase):
    def test_absent_service_files_autoissue(self) -> None:
        # grafana is a local (Windows-context) service; sonarqube moved to
        # Mint (see config/observability-services.json remote_services) and
        # is no longer in the local OBSERVABILITY_SERVICES list.
        rows = [r for r in _healthy_rows() if r["Service"] != "grafana"]
        out = StringIO()
        with _patch_service_state(rows):
            call_command("check_observability_health", stdout=out)
        output = out.getvalue()
        self.assertIn("status=degraded", output)
        self.assertIn("grafana", output)
        autoissues = AutoIssue.objects.filter(
            canonical_fingerprint__startswith="observability:grafana:absent"
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
        with _patch_service_state(rows):
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
        with _patch_service_state(rows):
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
        # alloy is a local service; pyroscope moved to Mint (remote_services).
        AutoIssue.objects.filter(
            canonical_fingerprint__startswith="observability:alloy:absent"
        ).delete()
        rows = [r for r in _healthy_rows() if r["Service"] != "alloy"]
        with _patch_service_state(rows):
            call_command("check_observability_health", stdout=StringIO())
            call_command("check_observability_health", stdout=StringIO())
            call_command("check_observability_health", stdout=StringIO())
        autoissues = AutoIssue.objects.filter(
            canonical_fingerprint__startswith="observability:alloy:absent"
        )
        self.assertEqual(autoissues.count(), 1)
        self.assertEqual(autoissues.first().occurrence_count, 3)


class DryRunTests(TestCase):
    def test_dry_run_does_not_file(self) -> None:
        before = AutoIssue.objects.count()
        rows = [r for r in _healthy_rows() if r["Service"] != "tempo"]
        out = StringIO()
        with _patch_service_state(rows):
            call_command("check_observability_health", "--dry-run", stdout=out)
        self.assertIn("status=degraded", out.getvalue())
        self.assertIn("tempo", out.getvalue())
        self.assertEqual(AutoIssue.objects.count(), before)
