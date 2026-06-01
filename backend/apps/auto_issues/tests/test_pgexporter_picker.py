"""Tests for the postgres-exporter picker (fetch -> evaluate -> file/resolve).

Uses SimpleTestCase (NO DB): the database seam (``upsert_dedup`` and
``AutoIssue.objects``) is mocked so every test runs in milliseconds. This keeps
the scoped-mutation gate fast — mutmut re-runs this whole file once per mutant,
so a 30s-per-test DB suite blew past the 30-minute mutation budget. The class
constants on ``AutoIssue`` stay real; only the manager and the dedup writer are
patched, so every line of pgexporter_picker.py is still exercised and its
mutants still die.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import urllib.error

from django.test import SimpleTestCase, override_settings

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import pgexporter_picker


def _manager(*, first=None, count=0, stale=()):
    """Build a chainable mock for ``AutoIssue.objects``.

    ``filter()`` and ``exclude()`` return the same chain so every call site
    (``_open_count``, ``_next_occurrence_count``, ``_resolve_recovered``)
    resolves against one configurable queryset. ``first``/``count``/iteration
    are the terminals each helper actually calls.
    """
    mgr = MagicMock(name="AutoIssue.objects")
    chain = MagicMock(name="qs")
    mgr.filter.return_value = chain
    chain.exclude.return_value = chain
    chain.first.return_value = first
    chain.count.return_value = count
    chain.__iter__.return_value = iter(list(stale))
    return mgr


class PickPgexporterFindingsTests(SimpleTestCase):
    def _run(self, text, *, manager=None, dry_run=False):
        mgr = manager if manager is not None else _manager()
        with patch.object(pgexporter_picker, "_fetch_metrics_text", return_value=text), \
                patch.object(pgexporter_picker, "upsert_dedup") as upsert, \
                patch.object(pgexporter_picker.AutoIssue, "objects", mgr):
            result = pgexporter_picker.pick_pgexporter_findings(dry_run=dry_run)
        return result, upsert

    def test_files_an_autoissue_for_each_finding(self):
        result, upsert = self._run("pg_up 0\n", manager=_manager(first=None, count=1))
        self.assertEqual(result["filed"], 1)
        self.assertEqual(upsert.call_count, 1)
        kwargs = upsert.call_args.kwargs
        self.assertEqual(kwargs["source"], AutoIssue.SOURCE_PROMETHEUS)
        self.assertEqual(kwargs["severity"], AutoIssue.SEVERITY_CRITICAL)
        self.assertIn("pg_up", kwargs["external_id"])
        self.assertEqual(kwargs["fingerprint"], "pgexporter:pg_up_down")
        self.assertTrue(kwargs["title"].startswith("[pgexporter]"))

    def test_priority_score_maps_from_severity(self):
        _, upsert = self._run("pg_up 0\n")
        self.assertAlmostEqual(upsert.call_args.kwargs["priority_score"], 0.95)

    def test_next_occurrence_count_increments_existing(self):
        existing = MagicMock(occurrence_count=4)
        with patch.object(pgexporter_picker.AutoIssue, "objects",
                          _manager(first=existing)):
            self.assertEqual(pgexporter_picker._next_occurrence_count("fp"), 5)

    def test_next_occurrence_count_is_one_when_missing(self):
        with patch.object(pgexporter_picker.AutoIssue, "objects", _manager(first=None)):
            self.assertEqual(pgexporter_picker._next_occurrence_count("fp"), 1)

    def test_next_occurrence_count_treats_null_count_as_zero(self):
        existing = MagicMock(occurrence_count=None)
        with patch.object(pgexporter_picker.AutoIssue, "objects",
                          _manager(first=existing)):
            self.assertEqual(pgexporter_picker._next_occurrence_count("fp"), 1)

    def test_resolve_recovered_resolves_each_stale_issue(self):
        issue = MagicMock()
        with patch.object(pgexporter_picker.AutoIssue, "objects",
                          _manager(stale=[issue])):
            resolved = pgexporter_picker._resolve_recovered({"still-active"})
        self.assertEqual(resolved, 1)
        self.assertEqual(issue.status, AutoIssue.STATUS_RESOLVED)
        self.assertEqual(issue.resolved_by, "pgexporter")
        self.assertIsNotNone(issue.resolved_at)
        self.assertIn("Trap:", issue.lessons_learned)
        self.assertIn("Fix shape:", issue.lessons_learned)
        issue.save.assert_called_once()
        self.assertEqual(
            issue.save.call_args.kwargs["update_fields"],
            ["status", "resolved_at", "resolved_by", "lessons_learned"],
        )

    def test_resolve_recovered_returns_zero_when_nothing_stale(self):
        with patch.object(pgexporter_picker.AutoIssue, "objects", _manager(stale=[])):
            self.assertEqual(pgexporter_picker._resolve_recovered(set()), 0)

    def test_open_count_reads_the_manager(self):
        with patch.object(pgexporter_picker.AutoIssue, "objects", _manager(count=7)):
            self.assertEqual(pgexporter_picker._open_count(), 7)

    def test_healthy_metrics_file_nothing(self):
        result, upsert = self._run("pg_up 1\n")
        self.assertEqual(result["filed"], 0)
        upsert.assert_not_called()

    def test_fetch_failure_is_handled_safely(self):
        with patch.object(pgexporter_picker, "_fetch_metrics_text",
                          side_effect=OSError("boom")), \
                patch.object(pgexporter_picker.AutoIssue, "objects", _manager(count=0)):
            result = pgexporter_picker.pick_pgexporter_findings()
        self.assertEqual(result["filed"], 0)
        self.assertEqual(result["resolved"], 0)
        self.assertEqual(result["would_file"], 0)

    def test_url_error_fetch_failure_is_handled_safely(self):
        with patch.object(pgexporter_picker, "_fetch_metrics_text",
                          side_effect=urllib.error.URLError("offline")), \
                patch.object(pgexporter_picker.AutoIssue, "objects", _manager()):
            result = pgexporter_picker.pick_pgexporter_findings()
        self.assertEqual(result["filed"], 0)
        self.assertEqual(result["resolved"], 0)

    @override_settings(PGEXPORTER_METRICS_URL="http://configured-exporter:9187/metrics")
    def test_default_metrics_url_comes_from_settings(self):
        seen = {}

        def fake_fetch(url):
            seen["url"] = url
            return "pg_up 1\n"

        with patch.object(pgexporter_picker, "_fetch_metrics_text", side_effect=fake_fetch), \
                patch.object(pgexporter_picker.AutoIssue, "objects", _manager()):
            result = pgexporter_picker.pick_pgexporter_findings()
        self.assertEqual(seen["url"], "http://configured-exporter:9187/metrics")
        self.assertEqual(result["filed"], 0)

    def test_explicit_metrics_url_argument_is_used(self):
        captured = {}

        def fake_fetch(url):
            captured["url"] = url
            return "pg_up 1\n"

        with patch.object(pgexporter_picker, "_fetch_metrics_text", side_effect=fake_fetch), \
                patch.object(pgexporter_picker.AutoIssue, "objects", _manager()):
            pgexporter_picker.pick_pgexporter_findings(metrics_url="http://explicit:9187/metrics")
        self.assertEqual(captured["url"], "http://explicit:9187/metrics")

    def test_dry_run_writes_nothing_but_reports_would_file(self):
        result, upsert = self._run("pg_up 0\n", dry_run=True)
        self.assertEqual(result["filed"], 0)
        self.assertEqual(result["would_file"], 1)
        upsert.assert_not_called()

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
