"""Tests for the pick_pgexporter_findings command (thin CLI wrapper).

SimpleTestCase + a mocked picker: the command's only job is to call the picker
and format its result, so no DB is needed. Methods are invoked DIRECTLY (not
via call_command) so coverage attributes every command line to these tests —
that is what lets mutation testing kill the command's mutants.
"""

from __future__ import annotations

import argparse
from io import StringIO
from unittest.mock import patch

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.auto_issues.management.commands import pick_pgexporter_findings as cmd_mod
from apps.auto_issues.management.commands.pick_pgexporter_findings import Command

_RESULT = {"filed": 2, "resolved": 1, "open": 3, "would_file": 4}


def _run_handle(*, dry_run: bool, metrics_url=None, result=None):
    captured = {}

    def fake_pick(url, *, dry_run):  # noqa: ARG001 - signature must match
        captured["url"] = url
        captured["dry_run"] = dry_run
        return result if result is not None else _RESULT

    with patch.object(cmd_mod, "pick_pgexporter_findings", side_effect=fake_pick):
        cmd = Command()
        cmd.stdout = StringIO()
        cmd.handle(metrics_url=metrics_url, dry_run=dry_run)
    return cmd.stdout.getvalue(), captured


class PickPgexporterCommandTests(SimpleTestCase):
    def test_handle_live_writes_full_marker(self):
        out, _ = _run_handle(dry_run=False)
        self.assertNotIn("dry-run", out)
        for fragment in ("filed=2", "resolved=1", "open=3", "would_file=4"):
            self.assertIn(fragment, out)

    def test_handle_dry_run_marks_dry_run(self):
        out, _ = _run_handle(dry_run=True, result={"filed": 0, "resolved": 0, "open": 0, "would_file": 7})
        self.assertIn("dry-run", out)
        self.assertIn("would_file=7", out)

    def test_handle_forwards_metrics_url_and_dry_run(self):
        _, captured = _run_handle(dry_run=True, metrics_url="http://custom:9187/metrics")
        self.assertEqual(captured["url"], "http://custom:9187/metrics")
        self.assertTrue(captured["dry_run"])

    def test_handle_forwards_none_url_when_unset(self):
        _, captured = _run_handle(dry_run=False, metrics_url=None)
        self.assertIsNone(captured["url"])
        self.assertFalse(captured["dry_run"])

    def test_call_command_uses_wrapper_and_writes_marker(self):
        with patch.object(cmd_mod, "pick_pgexporter_findings", return_value=_RESULT) as pick:
            out = StringIO()
            call_command("pick_pgexporter_findings", "--metrics-url", "http://x", stdout=out)
        pick.assert_called_once_with("http://x", dry_run=False)
        self.assertIn("[PGEXPORTER FINDINGS:", out.getvalue())

    def test_add_arguments_registers_both_flags(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        ns = parser.parse_args(["--dry-run", "--metrics-url", "http://x"])
        self.assertTrue(ns.dry_run)
        self.assertEqual(ns.metrics_url, "http://x")

    def test_add_arguments_defaults(self):
        parser = argparse.ArgumentParser()
        Command().add_arguments(parser)
        ns = parser.parse_args([])
        self.assertFalse(ns.dry_run)
        self.assertIsNone(ns.metrics_url)

    def test_help_describes_the_command(self):
        # Exact match: mutmut wraps string literals (XX...XX), which a substring
        # check would survive; equality kills that mutant.
        self.assertEqual(
            Command.help, "File AutoIssues for postgres-exporter health breaches."
        )
