"""Tests for coverage and mutation adapter helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from tools.coverage.lib.cobertura import line_rate
from tools.coverage.lib.paths import repo_path
from tools.mutation.lib.mutant_id import mutant_id
from tools.mutation.lib.quarantine import should_quarantine
from tools.mutation.lib.schema import mutation_summary


class QualityAdapterTests(unittest.TestCase):
    def test_cobertura_line_rate_is_percentage(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "coverage.xml"
            path.write_text('<coverage line-rate="0.875"></coverage>', encoding="utf-8")
            self.assertEqual(line_rate(path), 87.5)

    def test_repo_path_normalizes_windows_slashes(self) -> None:
        self.assertEqual(repo_path(".\\backend\\x.py"), "backend/x.py")

    def test_mutation_summary_marks_survivors(self) -> None:
        summary = mutation_summary("mutmut", killed=3, survived=1)
        self.assertEqual(summary["status"], "survivor")
        self.assertEqual(summary["score"], 0.75)

    def test_mutant_id_is_stable(self) -> None:
        self.assertEqual(
            mutant_id("mutmut", "a\\b.py", 4, "x"),
            mutant_id("mutmut", "a/b.py", 4, "x"),
        )

    def test_run_failures_are_quarantined(self) -> None:
        self.assertTrue(should_quarantine("run_failure"))
        self.assertFalse(should_quarantine("passed"))


if __name__ == "__main__":
    unittest.main()
