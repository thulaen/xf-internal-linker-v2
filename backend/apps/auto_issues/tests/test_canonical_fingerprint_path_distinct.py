"""Regression tests for AutoIssue #260 path-aware lesson fingerprints.

Source: docs/CPP-DAILY-ISSUE-PICKER-SPEC.md section
"Path-title separator for TDD lessons (AutoIssue #260)".
"""

from __future__ import annotations

import unittest

from apps.auto_issues.services.fingerprinting import canonical_fingerprint


class CanonicalFingerprintPathDistinctTests(unittest.TestCase):
    """Different repo paths must hash to different canonical fingerprints."""

    def test_two_paths_in_different_modules_produce_different_fingerprints(self):
        a = canonical_fingerprint(
            file="backend/apps/auto_issues/management/commands/decision_point.py",
            title="TDD lesson: decision_point marker shape",
        )
        b = canonical_fingerprint(
            file="backend/apps/core/management/commands/repair_restored_backup_schema.py",
            title="TDD lesson: repair_restored_backup_schema schema check",
        )

        self.assertNotEqual(
            a,
            b,
            (
                "AutoIssue #260: two distinct repo paths must produce two "
                "distinct canonical_fingerprints; collapsing them silently "
                "merges unrelated TDD lessons into one AutoIssue row."
            ),
        )

    def test_same_path_with_different_titles_produces_different_fingerprints(self):
        a = canonical_fingerprint(file="backend/apps/X/Y.py", title="Title A")
        b = canonical_fingerprint(file="backend/apps/X/Y.py", title="Title B")

        self.assertNotEqual(
            a,
            b,
            "the fingerprint must vary with the title even when the file is the same",
        )

    def test_same_path_and_title_produces_stable_fingerprint(self):
        a = canonical_fingerprint(file="backend/apps/X/Y.py", title="Title A")
        b = canonical_fingerprint(file="backend/apps/X/Y.py", title="Title A")

        self.assertEqual(
            a,
            b,
            "the fingerprint must be deterministic for stable dedup behavior",
        )

    def test_slash_direction_does_not_change_fingerprint(self):
        a = canonical_fingerprint(file="backend\\apps\\X\\Y.py", title="T")
        b = canonical_fingerprint(file="backend/apps/X/Y.py", title="T")

        self.assertEqual(
            a,
            b,
            (
                "logical path equivalence must collapse to one fingerprint; "
                "directory boundaries must not be stripped"
            ),
        )


if __name__ == "__main__":
    unittest.main()
