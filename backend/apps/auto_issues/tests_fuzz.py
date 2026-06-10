"""Tests for the fuzz picker — Phase 6 of the test-hardening plan."""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import fuzz


class FuzzPickerTests(TestCase):
    def test_missing_crashes_dir_returns_zero(self) -> None:
        # The crashes dir doesn't exist on a fresh checkout — the
        # libFuzzer CI job creates it. Picker must handle that gracefully.
        with patch.object(fuzz, "pick_fuzz_coverage_gaps", return_value=0):
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
            with patch.object(fuzz, "_resolve_stale_coverage_gaps", return_value=0):
                result = fuzz.pick_fuzz_coverage_gaps()
        self.assertIsInstance(result, int)
        self.assertGreaterEqual(result, 0)

    def test_coverage_gap_skips_when_no_extensions_dir(self) -> None:
        # When neither the resolved nor /repo path is a directory, the
        # picker returns 0 cleanly.
        with patch.object(fuzz, "_resolve", return_value=Path("/nonexistent")):
            with patch.object(Path, "is_dir", return_value=False):
                result = fuzz.pick_fuzz_coverage_gaps()
        self.assertEqual(result, 0)

    def test_coverage_gap_skips_empty_cpp_stub(self) -> None:
        with TemporaryDirectory() as tmp:
            ext_root = Path(tmp)
            (ext_root / "fuzz").mkdir()
            (ext_root / "pixie_walk.cpp").write_text("", encoding="utf-8")
            (ext_root / "real_kernel.cpp").write_text("int run() { return 1; }", encoding="utf-8")

            with patch.object(fuzz, "_resolve", return_value=ext_root):
                with patch.object(fuzz, "_upsert_coverage_gap", return_value=True) as upsert:
                    with patch.object(fuzz, "_resolve_stale_coverage_gaps", return_value=0):
                        result = fuzz.pick_fuzz_coverage_gaps()

        self.assertEqual(result, 1)
        upsert.assert_called_once()
        self.assertEqual(upsert.call_args.args[0], "real_kernel")


class FuzzCoverageGapResolutionTests(TestCase):
    def test_coverage_gap_resolves_when_target_exists(self) -> None:
        with TemporaryDirectory() as tmp:
            ext_root = Path(tmp)
            fuzz_dir = ext_root / "fuzz"
            fuzz_dir.mkdir()
            (ext_root / "real_kernel.cpp").write_text("int run() { return 1; }", encoding="utf-8")
            (fuzz_dir / "fuzz_real_kernel.cpp").write_text(
                "extern \"C\" int LLVMFuzzerTestOneInput(const unsigned char*, unsigned long) { return 0; }",
                encoding="utf-8",
            )
            issue = AutoIssue.objects.create(
                source=AutoIssue.SOURCE_FUZZ,
                external_id="coverage-gap:real_kernel",
                title="[fuzz-coverage-gap] real_kernel.cpp has no fuzz target",
            )

            with patch.object(fuzz, "_resolve", return_value=ext_root):
                result = fuzz.pick_fuzz_coverage_gaps()

        issue.refresh_from_db()
        self.assertEqual(result, 1)
        self.assertEqual(issue.status, AutoIssue.STATUS_RESOLVED)
        self.assertIn("Trap:", issue.lessons_learned)
        self.assertIn("Fix shape:", issue.lessons_learned)
