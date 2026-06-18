"""Tests for the Bazel affected-target helper."""

from __future__ import annotations

import unittest

from affected_targets import targets_for_paths


class AffectedTargetsTests(unittest.TestCase):
    def test_when_frontend_file_changes_then_frontend_target_returned(self) -> None:
        self.assertEqual(
            targets_for_paths(["frontend/src/app/embeddings/embeddings.component.ts"]),
            ["//frontend:runner_toolbox"],
        )

    def test_when_runner_file_changes_then_runner_tree_returned(self) -> None:
        self.assertEqual(
            targets_for_paths(["tools/runners/python/BUILD.bazel"]),
            ["//tools/runners/..."],
        )

    def test_when_unmapped_file_changes_then_no_fake_target_returned(self) -> None:
        self.assertEqual(targets_for_paths(["backend/apps/api/embedding_views.py"]), [])


if __name__ == "__main__":
    unittest.main()
