"""Tests for the always-on, drought-aware "fix N" quota rule.

The rule (confirmed with the operator): a commit is blocked while >= threshold
findings of a source are open, UNLESS at least `threshold` have been resolved
this session. A clean state (0 open) never blocks — you cannot be asked to fix
issues that do not exist.

    PASS iff  open_count < threshold  OR  resolved_count >= threshold
"""

from __future__ import annotations

from django.test import SimpleTestCase

from apps.auto_issues.services.always_on_quota import always_on_quota_status


class AlwaysOnQuotaStatusTests(SimpleTestCase):
    def test_zero_open_passes_even_with_zero_resolved(self):
        status = always_on_quota_status(open_count=0, resolved_count=0, threshold=10)
        self.assertTrue(status.ok)
        self.assertEqual(status.short, 0)

    def test_below_threshold_open_passes(self):
        status = always_on_quota_status(open_count=9, resolved_count=0, threshold=10)
        self.assertTrue(status.ok)
        self.assertEqual(status.short, 0)

    def test_at_threshold_open_with_no_resolved_blocks(self):
        status = always_on_quota_status(open_count=10, resolved_count=0, threshold=10)
        self.assertFalse(status.ok)
        self.assertEqual(status.short, 10)
        self.assertIn("10", status.message)

    def test_at_threshold_open_with_partial_resolved_blocks(self):
        status = always_on_quota_status(open_count=10, resolved_count=9, threshold=10)
        self.assertFalse(status.ok)
        self.assertEqual(status.short, 1)

    def test_many_open_but_threshold_resolved_passes(self):
        status = always_on_quota_status(open_count=25, resolved_count=10, threshold=10)
        self.assertTrue(status.ok)
        self.assertEqual(status.short, 0)

    def test_more_than_threshold_resolved_passes(self):
        status = always_on_quota_status(open_count=25, resolved_count=12, threshold=10)
        self.assertTrue(status.ok)

    def test_custom_threshold_is_respected(self):
        self.assertTrue(always_on_quota_status(open_count=4, resolved_count=0, threshold=5).ok)
        self.assertFalse(always_on_quota_status(open_count=5, resolved_count=0, threshold=5).ok)

    def test_negative_or_garbage_counts_are_coerced_safely(self):
        # Defensive: counts come from DB aggregates; never crash on odd input.
        status = always_on_quota_status(open_count=-3, resolved_count=-1, threshold=10)
        self.assertTrue(status.ok)
