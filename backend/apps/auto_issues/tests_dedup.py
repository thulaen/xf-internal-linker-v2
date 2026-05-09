"""Tests for cross-source dedup + internal-errors picker.

Goals (per the user's "no duplicates" mandate):
  - Same root cause captured by 3 sources lands on 1 AutoIssue row.
  - Re-running a picker is idempotent (no second row).
  - source_observations JSON tracks every source that observed the issue.
  - Severity escalation: max(severity) wins on merge.
  - priority_score escalation: max(priority_score) wins on merge.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.audit.models import ErrorLog
from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.internal_picker import pick_internal_issues


class CanonicalFingerprintTests(TestCase):
    def test_same_title_same_culprit_same_hash(self):
        a = canonical_fingerprint("RuntimeError: db down", "apps.audit.tasks:sync")
        b = canonical_fingerprint("RuntimeError: db down", "apps.audit.tasks:sync")
        self.assertEqual(a, b)

    def test_digit_runs_normalised(self):
        # `task 123 timed out` and `task 456 timed out` should hash the same.
        a = canonical_fingerprint("task 123 timed out", "")
        b = canonical_fingerprint("task 456 timed out", "")
        self.assertEqual(a, b)

    def test_paths_normalised(self):
        a = canonical_fingerprint("Cannot open /tmp/abc", "")
        b = canonical_fingerprint("Cannot open /tmp/xyz", "")
        self.assertEqual(a, b)

    def test_uuid_normalised(self):
        a = canonical_fingerprint(
            "Run 11111111-2222-3333-4444-555555555555 failed", ""
        )
        b = canonical_fingerprint(
            "Run aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee failed", ""
        )
        self.assertEqual(a, b)

    def test_different_titles_different_hash(self):
        a = canonical_fingerprint("RuntimeError: db down", "")
        b = canonical_fingerprint("RuntimeError: cache miss", "")
        self.assertNotEqual(a, b)


class CrossSourceDedupTests(TestCase):
    """The core 'no duplicates' guarantee: 3 sources → 1 row."""

    _CANONICAL = "abc123def4567890"

    def _upsert(self, *, source, external_id, severity="medium", score=0.5, count=1):
        return upsert_dedup(
            canonical=self._CANONICAL,
            source=source,
            external_id=external_id,
            fingerprint=f"{source}-fp",
            title="Same root-cause title across sources",
            description="desc",
            affected_files=["backend/apps/audit/tasks.py"],
            severity=severity,
            priority_score=score,
            occurrence_count=count,
        )

    def test_first_source_creates_row(self):
        row, outcome = self._upsert(source="glitchtip", external_id="gt-1")
        self.assertEqual(outcome, "created")
        self.assertEqual(AutoIssue.objects.count(), 1)
        self.assertEqual(len(row.source_observations), 1)

    def test_second_source_merges_into_existing_row(self):
        self._upsert(source="glitchtip", external_id="gt-1")
        row, outcome = self._upsert(source="agent", external_id="fp-internal-1")
        self.assertEqual(outcome, "merged")
        self.assertEqual(AutoIssue.objects.count(), 1, "no duplicate row")
        self.assertEqual(len(row.source_observations), 2)
        sources = {obs["source"] for obs in row.source_observations}
        self.assertEqual(sources, {"glitchtip", "agent"})

    def test_third_source_also_merges(self):
        self._upsert(source="glitchtip", external_id="gt-1")
        self._upsert(source="agent", external_id="fp-internal-1")
        row, outcome = self._upsert(source="pyroscope", external_id="py-fn-1")
        self.assertEqual(outcome, "merged")
        self.assertEqual(AutoIssue.objects.count(), 1)
        self.assertEqual(len(row.source_observations), 3)

    def test_re_observation_same_source_updates_not_duplicates(self):
        self._upsert(source="glitchtip", external_id="gt-1", count=5)
        row, outcome = self._upsert(source="glitchtip", external_id="gt-1", count=8)
        self.assertEqual(outcome, "updated")
        self.assertEqual(len(row.source_observations), 1)
        self.assertEqual(row.source_observations[0]["occurrence_count"], 8)

    def test_severity_escalates_on_merge(self):
        self._upsert(source="glitchtip", external_id="gt-1", severity="medium")
        row, _ = self._upsert(
            source="agent", external_id="fp-1", severity="critical"
        )
        self.assertEqual(row.severity, "critical")

    def test_priority_score_escalates_on_merge(self):
        self._upsert(source="glitchtip", external_id="gt-1", score=0.4)
        row, _ = self._upsert(source="agent", external_id="fp-1", score=0.85)
        self.assertEqual(row.priority_score, 0.85)

    def test_resolved_row_does_not_block_new_observation(self):
        """If a prior observation was resolved, a fresh re-observation
        should create a NEW row (this is the regression path — same
        canonical, but new ticket)."""
        first, _ = self._upsert(source="glitchtip", external_id="gt-1")
        first.status = AutoIssue.STATUS_RESOLVED
        first.save()
        second, outcome = self._upsert(source="agent", external_id="fp-1")
        self.assertEqual(outcome, "created")
        self.assertEqual(AutoIssue.objects.count(), 2)


class InternalPickerTests(TestCase):
    def test_no_internal_rows_returns_zero_promoted(self):
        result = pick_internal_issues()
        self.assertEqual(
            result,
            {
                "status": "ok",
                "fetched": 0,
                "promoted": 0,
                "created": 0,
                "merged": 0,
                "updated": 0,
            },
        )

    def test_promotes_internal_row_into_auto_issues(self):
        ErrorLog.objects.create(
            source=ErrorLog.SOURCE_INTERNAL,
            error_message="OperationalError: pool timeout",
            fingerprint="internal-fp-1",
            severity="high",
            occurrence_count=4,
            acknowledged=False,
        )
        result = pick_internal_issues()
        self.assertEqual(result["fetched"], 1)
        self.assertEqual(result["promoted"], 1)
        self.assertEqual(AutoIssue.objects.count(), 1)
        row = AutoIssue.objects.first()
        self.assertEqual(row.source, AutoIssue.SOURCE_AGENT)
        self.assertTrue(row.canonical_fingerprint)
        self.assertEqual(len(row.source_observations), 1)

    def test_internal_then_glitchtip_same_title_merge_into_one_row(self):
        """The headline test: same title from two sources = one row."""
        ErrorLog.objects.create(
            source=ErrorLog.SOURCE_INTERNAL,
            error_message="ValueError: bad input",
            fingerprint="internal-fp-1",
            severity="medium",
            occurrence_count=2,
            acknowledged=False,
        )
        result = pick_internal_issues()
        self.assertEqual(result["created"], 1)
        # Now simulate the glitchtip_picker upserting a row with the same
        # title — this should MERGE, not duplicate.
        canonical = canonical_fingerprint("ValueError: bad input", "")
        upsert_dedup(
            canonical=canonical,
            source="glitchtip",
            external_id="gt-99",
            fingerprint="gt-fp-99",
            title="ValueError: bad input",
            description="from gt",
            affected_files=[],
            severity="medium",
            priority_score=0.6,
            occurrence_count=3,
        )
        self.assertEqual(
            AutoIssue.objects.count(),
            1,
            "two sources, one root cause → must be one row",
        )
        row = AutoIssue.objects.first()
        observed_sources = {obs["source"] for obs in row.source_observations}
        self.assertEqual(observed_sources, {"agent", "glitchtip"})
