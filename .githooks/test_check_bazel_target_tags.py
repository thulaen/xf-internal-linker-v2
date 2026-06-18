"""Tests for the Bazel tag checker."""

from __future__ import annotations

import importlib.util
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).with_name("check-bazel-target-tags.py")
SPEC = importlib.util.spec_from_file_location("check_bazel_target_tags", HOOK)
mod = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(mod)


class BazelTargetTagTests(unittest.TestCase):
    def test_test_target_without_tags_is_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BUILD.bazel"
            path.write_text('py_test(\n    name = "x",\n)\n', encoding="utf-8")
            self.assertTrue(mod.find_missing_tags(path))

    def test_test_target_with_tags_passes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "BUILD.bazel"
            path.write_text(
                'py_test(\n    name = "x",\n    tags = ["dell"],\n)\n',
                encoding="utf-8",
            )
            self.assertEqual(mod.find_missing_tags(path), [])


if __name__ == "__main__":
    unittest.main()
