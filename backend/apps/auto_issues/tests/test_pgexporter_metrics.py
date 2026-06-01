"""Tests for the pure postgres-exporter metric parser and threshold rules.

No DB, no network — these run in SimpleTestCase. The parser turns Prometheus
text-exposition format into Sample rows; evaluate_rules turns Samples into
Findings using cited PostgreSQL health thresholds (see
docs/specs/fr-pgexporter-autoissues.md).
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.pgexporter_metrics import (
    Finding,
    Sample,
    evaluate_rules,
    parse_prometheus_text,
)

_SAMPLE_TEXT = """\
# HELP pg_up Whether the last scrape of metrics from PostgreSQL was able to connect to the server.
# TYPE pg_up gauge
pg_up 1
# HELP pg_database_size_bytes Disk space used by the database
# TYPE pg_database_size_bytes gauge
pg_database_size_bytes{datname="xf_linker"} 8.1032883e+07
pg_locks_count{datname="xf_linker",mode="accessexclusivelock"} 2
"""


class ParsePrometheusTextTests(SimpleTestCase):
    def test_skips_help_type_and_blank_lines(self):
        samples = parse_prometheus_text(_SAMPLE_TEXT)
        names = {s.name for s in samples}
        self.assertEqual(names, {"pg_up", "pg_database_size_bytes", "pg_locks_count"})

    def test_parses_value_with_scientific_notation(self):
        samples = parse_prometheus_text(_SAMPLE_TEXT)
        size = next(s for s in samples if s.name == "pg_database_size_bytes")
        self.assertAlmostEqual(size.value, 8.1032883e07)
        self.assertEqual(size.labels, {"datname": "xf_linker"})

    def test_parses_unlabelled_metric(self):
        samples = parse_prometheus_text(_SAMPLE_TEXT)
        up = next(s for s in samples if s.name == "pg_up")
        self.assertEqual(up.value, 1.0)
        self.assertEqual(up.labels, {})

    def test_parses_multiple_labels(self):
        samples = parse_prometheus_text(_SAMPLE_TEXT)
        lock = next(s for s in samples if s.name == "pg_locks_count")
        self.assertEqual(lock.labels, {"datname": "xf_linker", "mode": "accessexclusivelock"})
        self.assertEqual(lock.value, 2.0)

    def test_ignores_malformed_lines_without_crashing(self):
        samples = parse_prometheus_text("garbage_no_value\npg_up 1\n")
        self.assertEqual([s.name for s in samples], ["pg_up"])

    def test_handles_nan_and_inf_values(self):
        samples = parse_prometheus_text("pg_x 1\npg_nan NaN\npg_inf +Inf\n")
        by = {s.name: s.value for s in samples}
        self.assertEqual(by["pg_x"], 1.0)
        self.assertTrue(by["pg_nan"] != by["pg_nan"])  # NaN
        self.assertEqual(by["pg_inf"], float("inf"))

    def test_line_with_non_numeric_value_is_skipped(self):
        # Matches the name/value shape but the value is not a float -> dropped.
        samples = parse_prometheus_text("pg_up 1\npg_bogus not_a_number\n")
        self.assertEqual([s.name for s in samples], ["pg_up"])


class EvaluateRulesTests(SimpleTestCase):
    def test_pg_down_is_critical(self):
        findings = evaluate_rules([Sample("pg_up", {}, 0.0)])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, AutoIssue.SEVERITY_CRITICAL)
        self.assertIn("pg_up", findings[0].fingerprint)

    def test_pg_up_healthy_yields_no_finding(self):
        self.assertEqual(evaluate_rules([Sample("pg_up", {}, 1.0)]), [])

    def test_deadlocks_above_zero_is_high(self):
        findings = evaluate_rules([
            Sample("pg_stat_database_deadlocks", {"datname": "xf_linker"}, 3.0),
        ])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, AutoIssue.SEVERITY_HIGH)
        self.assertIn("xf_linker", findings[0].title)

    def test_deadlocks_on_template_db_is_ignored(self):
        self.assertEqual(
            evaluate_rules([Sample("pg_stat_database_deadlocks", {"datname": "template0"}, 5.0)]),
            [],
        )

    def test_low_cache_hit_ratio_is_medium(self):
        findings = evaluate_rules([
            Sample("pg_stat_database_blks_hit", {"datname": "xf_linker"}, 50.0),
            Sample("pg_stat_database_blks_read", {"datname": "xf_linker"}, 50.0),
        ])
        self.assertEqual(len(findings), 1)
        self.assertEqual(findings[0].severity, AutoIssue.SEVERITY_MEDIUM)

    def test_high_cache_hit_ratio_yields_no_finding(self):
        findings = evaluate_rules([
            Sample("pg_stat_database_blks_hit", {"datname": "xf_linker"}, 9990.0),
            Sample("pg_stat_database_blks_read", {"datname": "xf_linker"}, 10.0),
        ])
        self.assertEqual(findings, [])

    def test_cache_rule_skips_system_databases(self):
        findings = evaluate_rules([
            Sample("pg_stat_database_blks_hit", {"datname": "template0"}, 50.0),
            Sample("pg_stat_database_blks_read", {"datname": "template0"}, 50.0),
        ])
        self.assertEqual(findings, [])

    def test_low_read_volume_skips_cache_rule(self):
        # Too few reads to judge cache health — no noisy finding.
        findings = evaluate_rules([
            Sample("pg_stat_database_blks_hit", {"datname": "xf_linker"}, 1.0),
            Sample("pg_stat_database_blks_read", {"datname": "xf_linker"}, 1.0),
        ])
        self.assertEqual(findings, [])

    def test_cache_rule_treats_missing_reads_as_zero(self):
        findings = evaluate_rules([
            Sample("pg_stat_database_blks_hit", {"datname": "xf_linker"}, 200.0),
        ])
        self.assertEqual(findings, [])

    def test_connection_saturation_is_high(self):
        findings = evaluate_rules([
            Sample("pg_stat_activity_count", {"datname": "xf_linker", "state": "active"}, 90.0),
            Sample("pg_settings_max_connections", {}, 100.0),
        ])
        self.assertTrue(any(f.severity == AutoIssue.SEVERITY_HIGH for f in findings))

    def test_connection_saturation_zero_limit_returns_no_finding(self):
        # Covers the guard branch: limit <= 0 should not divide-by-zero or raise.
        findings = evaluate_rules([
            Sample("pg_stat_activity_count", {"datname": "xf_linker", "state": "active"}, 5.0),
            Sample("pg_settings_max_connections", {}, 0.0),
        ])
        saturation_findings = [f for f in findings if f.key == "connection_saturation"]
        self.assertEqual(saturation_findings, [])

    def test_findings_are_stable_and_unique_by_fingerprint(self):
        samples = [
            Sample("pg_up", {}, 0.0),
            Sample("pg_stat_database_deadlocks", {"datname": "xf_linker"}, 1.0),
        ]
        a = {f.fingerprint for f in evaluate_rules(samples)}
        b = {f.fingerprint for f in evaluate_rules(samples)}
        self.assertEqual(a, b)
        self.assertEqual(len(a), 2)

    def test_every_finding_is_the_finding_dataclass(self):
        for f in evaluate_rules([Sample("pg_up", {}, 0.0)]):
            self.assertIsInstance(f, Finding)
