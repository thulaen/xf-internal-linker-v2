"""Tests for the print_open_snapshots management command."""

from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import SimpleTestCase

from apps.auto_issues.management.commands.print_open_snapshots import (
    _SnapshotdUnavailable,
)


class PrintOpenSnapshotsCommandTests(SimpleTestCase):
    def test_snapshotd_unavailable_prints_skipped_marker(self) -> None:
        out = StringIO()

        with mock.patch(
            "apps.auto_issues.management.commands.print_open_snapshots.Command._collect_picks",
            side_effect=_SnapshotdUnavailable("snapshotd test unavailable"),
        ):
            call_command("print_open_snapshots", stdout=out)

        self.assertEqual(
            out.getvalue().strip(),
            "[SNAPSHOTS READ: skipped — snapshotd unavailable]",
        )
