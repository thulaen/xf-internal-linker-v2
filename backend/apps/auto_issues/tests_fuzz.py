"""Tests for the fuzz picker — Phase 6 of the test-hardening plan."""

from __future__ import annotations

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
