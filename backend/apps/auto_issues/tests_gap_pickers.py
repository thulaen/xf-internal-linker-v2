"""Tests for the gap-filler pickers added 2026-05-09.

Covers:
  - slow_query_picker noise filter
  - disk_pressure_picker thresholds
  - slo_probe_picker classification
  - missed_runs_picker
  - deploy_check_picker parsing
  - output_quality_picker resolve + threshold logic
"""

from __future__ import annotations

from datetime import timedelta
from unittest import mock

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.deploy_check_picker import _parse_findings
from apps.auto_issues.services.disk_pressure_picker import (
    _DiskCheck,
    _severity_for as _disk_severity,
)
from apps.auto_issues.services.missed_runs_picker import pick_missed_runs
from apps.auto_issues.services.slo_probe_picker import (
    _Probe,
    _classify as _slo_classify,
)
from apps.auto_issues.services.slow_query_picker import _is_app_query


class SlowQueryNoiseFilterTests(SimpleTestCase):
    def test_postgres_exporter_query_is_filtered(self):
        q = "SELECT current_database() datname, schemaname, relname, ..."
        self.assertFalse(_is_app_query(q))

    def test_pg_stat_internal_filtered(self):
        self.assertFalse(_is_app_query("SELECT * FROM pg_stat_user_tables"))
        self.assertFalse(_is_app_query("SELECT pg_database_size('xf_linker')"))

    def test_app_query_passes(self):
        q = "SELECT * FROM auto_issues_autoissue WHERE status='open'"
        self.assertTrue(_is_app_query(q))

    def test_information_schema_filtered(self):
        self.assertFalse(_is_app_query("SELECT * FROM information_schema.tables"))


class DiskPressureThresholdTests(SimpleTestCase):
    def test_below_warn_returns_none(self):
        target = _DiskCheck("test", "/tmp", warn_pct=80.0, crit_pct=90.0)
        self.assertIsNone(_disk_severity(50.0, target))

    def test_warn_band(self):
        target = _DiskCheck("test", "/tmp", warn_pct=80.0, crit_pct=90.0)
        self.assertEqual(_disk_severity(85.0, target), AutoIssue.SEVERITY_MEDIUM)

    def test_critical_band(self):
        target = _DiskCheck("test", "/tmp", warn_pct=80.0, crit_pct=90.0)
        self.assertEqual(_disk_severity(95.0, target), AutoIssue.SEVERITY_HIGH)


class SLOClassifyTests(SimpleTestCase):
    _PROBE = _Probe("p", "http://x/", "GET", (200,), 1000.0)

    def test_healthy_returns_none(self):
        sev, _ = _slo_classify(self._PROBE, 200, 100.0, None)
        self.assertIsNone(sev)

    def test_connection_error_high(self):
        sev, reason = _slo_classify(self._PROBE, None, 100.0, "timeout")
        self.assertEqual(sev, AutoIssue.SEVERITY_HIGH)
        self.assertIn("connection error", reason)

    def test_status_mismatch_high(self):
        sev, _ = _slo_classify(self._PROBE, 503, 100.0, None)
        self.assertEqual(sev, AutoIssue.SEVERITY_HIGH)

    def test_latency_breach_medium(self):
        sev, reason = _slo_classify(self._PROBE, 200, 5000.0, None)
        self.assertEqual(sev, AutoIssue.SEVERITY_MEDIUM)
        self.assertIn("latency", reason)


class DeployCheckParserTests(SimpleTestCase):
    _SAMPLE_OUTPUT = """\
?: (security.W018) You should not have DEBUG set to True in deployment.
?: (security.W004) You have not set a value for the SECURE_HSTS_SECONDS setting.
"""

    def test_parses_two_findings(self):
        out = _parse_findings(self._SAMPLE_OUTPUT)
        self.assertEqual(len(out), 2)
        ids = [f[0] for f in out]
        self.assertIn("security.W018", ids)
        self.assertIn("security.W004", ids)

    def test_levels_extracted(self):
        out = _parse_findings(self._SAMPLE_OUTPUT)
        self.assertTrue(all(f[1] == "W" for f in out))

    def test_empty_output_returns_empty(self):
        self.assertEqual(_parse_findings(""), [])


class MissedRunsPickerTests(TestCase):
    def test_no_alerts_returns_zero(self):
        result = pick_missed_runs()
        self.assertEqual(
            result,
            {
                "status": "ok",
                "alerts": 0,
                "promoted": 0,
                "created": 0,
                "merged": 0,
                "updated": 0,
            },
        )

    def test_promotes_unacked_alert(self):
        from apps.scheduled_updates.models import JobAlert

        JobAlert.objects.create(
            job_key="test-job",
            alert_type="failed",
            calendar_date=timezone.now().date(),
        )
        result = pick_missed_runs()
        self.assertEqual(result["alerts"], 1)
        self.assertEqual(result["created"], 1)
        # AutoIssue row created with the right shape.
        row = AutoIssue.objects.filter(external_id="missed-test-job-failed").first()
        self.assertIsNotNone(row)
        self.assertEqual(row.severity, AutoIssue.SEVERITY_HIGH)

    def test_acked_alert_skipped(self):
        from apps.scheduled_updates.models import JobAlert

        JobAlert.objects.create(
            job_key="acked-job",
            alert_type="missed",
            calendar_date=timezone.now().date(),
            acknowledged_at=timezone.now(),
        )
        self.assertEqual(pick_missed_runs()["alerts"], 0)


class OutputQualityResolveTests(SimpleTestCase):
    """Module-level callables exist + resolve via the picker's importer."""

    def test_resolve_callable_for_real_metric(self):
        from apps.auto_issues.services.output_quality_picker import (
            _resolve_callable,
            _metric_errorlog_ack_rate,
        )

        fn = _resolve_callable(
            "apps.auto_issues.services.output_quality_picker:_metric_errorlog_ack_rate"
        )
        self.assertIs(fn, _metric_errorlog_ack_rate)

    def test_resolve_returns_none_for_garbage(self):
        from apps.auto_issues.services.output_quality_picker import _resolve_callable

        self.assertIsNone(_resolve_callable("nonexistent.module:nope"))
