"""Tests for the verify_always_on_quota management command (DB counts -> gate)."""

from __future__ import annotations

from io import StringIO

import argparse

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.management.commands.verify_always_on_quota import (
    Command as VerifyCommand,
    _parse_cutoff,
)
from apps.auto_issues.services.always_on_quota import DEFAULT_THRESHOLD


class VerifyAlwaysOnQuotaArgTests(SimpleTestCase):
    """Direct (no-DB) tests of the command's arg parsing + cutoff helper, so
    mutation testing can attribute and kill the add_arguments mutants."""

    def _parser(self) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser()
        VerifyCommand().add_arguments(parser)
        return parser

    def test_source_is_required(self):
        with self.assertRaises(SystemExit):
            self._parser().parse_args([])

    def test_threshold_defaults_and_parses_as_int(self):
        ns = self._parser().parse_args(["--source", "prometheus"])
        self.assertEqual(ns.source, "prometheus")
        self.assertEqual(ns.threshold, DEFAULT_THRESHOLD)
        ns2 = self._parser().parse_args(["--source", "compiler", "--threshold", "7"])
        self.assertEqual(ns2.threshold, 7)
        self.assertIsInstance(ns2.threshold, int)

    def test_resolved_after_flag(self):
        ns = self._parser().parse_args(["--source", "x", "--resolved-after", "2026-05-30 06:00"])
        self.assertEqual(ns.resolved_after, "2026-05-30 06:00")

    def test_parse_cutoff_none_and_valid_and_invalid(self):
        self.assertIsNone(_parse_cutoff(None))
        self.assertIsNone(_parse_cutoff(""))
        self.assertIsNotNone(_parse_cutoff("2026-05-30 06:00"))
        with self.assertRaises(CommandError):
            _parse_cutoff("not-a-date")


def _make(source: str, *, n: int, status: str) -> None:
    for i in range(n):
        AutoIssue.objects.create(
            source=source,
            status=status,
            title=f"x{i}",
            description="d",
            severity=AutoIssue.SEVERITY_LOW,
            external_id=f"{source}:{status}:{i}",
            canonical_fingerprint=f"{source}-{status}-{i}",
            resolved_at=timezone.now() if status == AutoIssue.STATUS_RESOLVED else None,
            lessons_learned="Trap: x Fix shape: y" if status == AutoIssue.STATUS_RESOLVED else "",
        )


class VerifyAlwaysOnQuotaCommandTests(TestCase):
    def test_passes_when_open_below_threshold(self):
        _make(AutoIssue.SOURCE_PROMETHEUS, n=9, status=AutoIssue.STATUS_OPEN)
        out = StringIO()
        call_command("verify_always_on_quota", "--source", "prometheus", "--threshold", "10", stdout=out)
        self.assertIn("ALWAYS-ON QUOTA VERIFIED", out.getvalue())

    def test_passes_when_zero_open(self):
        out = StringIO()
        call_command("verify_always_on_quota", "--source", "prometheus", "--threshold", "10", stdout=out)
        self.assertIn("ALWAYS-ON QUOTA VERIFIED", out.getvalue())

    def test_blocks_when_ten_open_and_none_resolved(self):
        _make(AutoIssue.SOURCE_PROMETHEUS, n=10, status=AutoIssue.STATUS_OPEN)
        with self.assertRaises(CommandError) as ctx:
            call_command("verify_always_on_quota", "--source", "prometheus", "--threshold", "10")
        self.assertIn("resolve", str(ctx.exception).lower())

    def test_passes_when_ten_resolved_after_cutoff(self):
        _make(AutoIssue.SOURCE_PROMETHEUS, n=25, status=AutoIssue.STATUS_OPEN)
        _make(AutoIssue.SOURCE_PROMETHEUS, n=10, status=AutoIssue.STATUS_RESOLVED)
        out = StringIO()
        call_command(
            "verify_always_on_quota", "--source", "prometheus", "--threshold", "10",
            "--resolved-after", "2000-01-01 00:00", stdout=out,
        )
        self.assertIn("ALWAYS-ON QUOTA VERIFIED", out.getvalue())

    def test_only_named_source_counts(self):
        _make(AutoIssue.SOURCE_GLITCHTIP, n=20, status=AutoIssue.STATUS_OPEN)
        out = StringIO()
        call_command("verify_always_on_quota", "--source", "prometheus", "--threshold", "10", stdout=out)
        self.assertIn("ALWAYS-ON QUOTA VERIFIED", out.getvalue())
