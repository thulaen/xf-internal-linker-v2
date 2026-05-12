"""Tests for the fuzz picker — Phase 6 of the test-hardening plan."""

from __future__ import annotations

from unittest.mock import patch

from django.test import SimpleTestCase

from apps.auto_issues.services import fuzz


class FuzzPickerTests(SimpleTestCase):
    def test_missing_crashes_dir_returns_zero(self) -> None:
        # The crashes dir doesn't exist on a fresh checkout — the
        # libFuzzer CI job creates it. Picker must handle that gracefully.
        self.assertEqual(fuzz.pick_fuzz_crashes(), 0)

    def test_kind_from_filename(self) -> None:
        self.assertEqual(fuzz._kind_from_filename("crash-abc123"), "crash")
        self.assertEqual(fuzz._kind_from_filename("oom-deadbeef"), "oom")
        self.assertEqual(fuzz._kind_from_filename("leak-f00d"), "leak")
        self.assertEqual(fuzz._kind_from_filename("timeout-cafe"), "timeout")
        self.assertEqual(fuzz._kind_from_filename("README.md"), "")
        self.assertEqual(fuzz._kind_from_filename(""), "")

    def test_coverage_gap_returns_int_with_db_mock(self) -> None:
        # The coverage-gap picker is best-effort. We mock the upsert so
        # the test doesn't need a real DB (SimpleTestCase forbids DB).
        with patch.object(fuzz, "_upsert_coverage_gap", return_value=True):
            result = fuzz.pick_fuzz_coverage_gaps()
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)

    def test_coverage_gap_skips_when_no_extensions_dir(self) -> None:
        # When neither the resolved nor /repo path is a directory, the
        # picker returns 0 cleanly.
        from pathlib import Path
        with patch.object(fuzz, "_resolve", return_value=Path("/nonexistent")):
            with patch.object(Path, "is_dir", return_value=False):
                result = fuzz.pick_fuzz_coverage_gaps()
        self.assertEqual(result, 0)
