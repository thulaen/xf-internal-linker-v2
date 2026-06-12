"""Tests for the print_open_snapshots management command.

The Go snapshotd daemon was retired on 2026-06-11 (ADR 0007); the
command now always emits the skipped marker form, which the session
ritual hooks accept. These tests pin that contract.
"""

from __future__ import annotations

from io import StringIO

from django.core.management import call_command
from django.test import SimpleTestCase


class PrintOpenSnapshotsCommandTests(SimpleTestCase):
    def test_prints_the_skipped_marker(self) -> None:
        out = StringIO()

        call_command("print_open_snapshots", stdout=out)

        self.assertEqual(
            out.getvalue().strip(),
            "[SNAPSHOTS READ: skipped — snapshotd unavailable]",
        )

    def test_legacy_flags_are_still_accepted(self) -> None:
        # Call sites pass --by-severity / --top; they must not error even
        # though the snapshot store is gone.
        out = StringIO()

        call_command("print_open_snapshots", "--by-severity", "--top", "5", stdout=out)

        self.assertIn("[SNAPSHOTS READ:", out.getvalue())
