"""Tests for shared profiling-proof marker constants and edge cases."""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.profiling_proof_shared import (
    NATIVE_REWRITE_LABEL,
    NATIVE_REWRITE_REQUIRED_FIELDS,
    PROFILE_GAP_CATEGORIES,
    PROFILE_GAP_CATEGORY_TEXT,
    PROFILE_PROOF_DECISIONS,
)


class ProfilingProofSharedTests(SimpleTestCase):
    def test_gap_categories_match_required_marker_text(self) -> None:
        self.assertEqual(PROFILE_GAP_CATEGORY_TEXT, ",".join(PROFILE_GAP_CATEGORIES))
        self.assertIn("trace-profile-correlation", PROFILE_GAP_CATEGORIES)

    def test_decisions_cover_not_achievable_path(self) -> None:
        self.assertIn("not-achievable", PROFILE_PROOF_DECISIONS)

    def test_native_rewrite_marker_requires_reuse_and_fallback_fields(self) -> None:
        self.assertEqual(NATIVE_REWRITE_LABEL, "performance-native-rewrite")
        self.assertTrue(
            {"autoissue", "label", "rollback", "reuse_check"}.issubset(
                NATIVE_REWRITE_REQUIRED_FIELDS
            )
        )
        self.assertTrue(
            {"canonical", "default_path", "python_fallback"}.issubset(
                NATIVE_REWRITE_REQUIRED_FIELDS
            )
        )
