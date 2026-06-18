"""Tests for the small Bazel generator helpers."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from lib.bazel_gen import render_exports_files, write_if_changed
from gen_bazel_frontend import missing_snippets


class BazelGeneratorTests(unittest.TestCase):
    def test_exports_are_sorted_and_deduped(self) -> None:
        content = render_exports_files(["b.txt", "a.txt", "b.txt"])
        self.assertLess(content.index('"a.txt"'), content.index('"b.txt"'))
        self.assertEqual(content.count('"b.txt"'), 1)

    def test_write_if_changed_reports_second_write_as_unchanged(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / "BUILD.bazel"
            self.assertTrue(write_if_changed(target, "x\n"))
            self.assertFalse(write_if_changed(target, "x\n"))

    def test_frontend_check_reports_missing_required_snippets(self) -> None:
        self.assertEqual(missing_snippets("npm_link_all_packages"), ["runner_toolbox", "package-lock.json"])


if __name__ == "__main__":
    unittest.main()
