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
from unittest.mock import patch

from django.test import SimpleTestCase, TestCase
from django.utils import timezone

from apps.audit.models import ErrorLog
from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services import dedup as dedup_service
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint
from apps.auto_issues.services.internal_picker import pick_internal_issues


class CanonicalFingerprintTests(SimpleTestCase):
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

    def setUp(self):
        AutoIssue.objects.all().delete()

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

    def test_same_source_external_id_updates_when_canonical_changes(self):
        self._upsert(source="loki", external_id="loki:hot::abc", count=5)

        row, outcome = upsert_dedup(
            canonical="different-canonical-after-log-sample-changed",
            source="loki",
            external_id="loki:hot::abc",
            fingerprint="loki-fp",
            title="Same Loki fingerprint with a new sample title",
            description="desc",
            affected_files=[],
            severity="medium",
            priority_score=0.8,
            occurrence_count=12,
        )

        self.assertEqual(outcome, "updated")
        self.assertEqual(AutoIssue.objects.count(), 1)
        self.assertEqual(row.source_observations[0]["occurrence_count"], 12)

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

    def test_resolved_same_source_external_id_merges_back(self):
        """Lines 220-221: when only a RESOLVED row matches (source, external_id),
        the new observation merges into that resolved row ('merged-resolved')."""
        # Create and resolve a row with a specific (source, external_id)
        resolved, _ = self._upsert(source="glitchtip", external_id="gt-resolved-1")
        resolved.status = AutoIssue.STATUS_RESOLVED
        resolved.save()

        # Re-observe with a DIFFERENT canonical so open-row lookup misses,
        # but the same (source, external_id) so the resolved-path triggers.
        row, outcome = upsert_dedup(
            canonical="totally-different-canonical-xyz",
            source="glitchtip",
            external_id="gt-resolved-1",
            fingerprint="glitchtip-fp",
            title="Same external_id re-observed after resolve",
            description="desc",
            affected_files=["backend/apps/auto_issues/models.py"],
            severity="medium",
            priority_score=0.6,
            occurrence_count=2,
        )
        self.assertEqual(outcome, "merged-resolved")
        # No new row created — the resolved row is reused in-place.
        self.assertEqual(AutoIssue.objects.count(), 1)

    def test_upsert_with_empty_affected_files_adopts_new_files(self):
        """Line 145: when an existing row has no affected_files, the new observation's
        files should be adopted into the existing row."""
        row, _ = upsert_dedup(
            canonical=self._CANONICAL,
            source="glitchtip",
            external_id="gt-empty-files",
            fingerprint="glitchtip-fp",
            title="Issue with no affected files initially",
            description="desc",
            affected_files=[],  # empty — so existing row has no files
            severity="medium",
            priority_score=0.4,
            occurrence_count=1,
        )
        self.assertEqual(row.affected_files, [])

        # Second observation brings file info — should be adopted (line 145)
        row2, outcome = upsert_dedup(
            canonical=self._CANONICAL,
            source="agent",
            external_id="agent-with-files",
            fingerprint="agent-fp",
            title="Same root cause with file info",
            description="desc",
            affected_files=["backend/apps/auto_issues/models.py"],
            severity="medium",
            priority_score=0.4,
            occurrence_count=1,
        )
        row2.refresh_from_db()
        self.assertEqual(row2.affected_files, ["backend/apps/auto_issues/models.py"])

    def test_canonical_lookup_takes_row_lock_before_create(self):
        """Bug 4 fix: canonical lookup must use select_for_update before create."""

        class LockProbeQuery:
            locked = False

            def filter(self, **_kwargs):
                return self

            def select_for_update(self):
                self.locked = True
                return self

            def exclude(self, **_kwargs):
                return self

            def first(self):
                if not self.locked:
                    raise AssertionError("canonical lookup did not take a row lock")
                return None

        probe = LockProbeQuery()
        sentinel = object()
        with (
            patch.object(dedup_service.AutoIssue, "objects", probe),
            patch.object(dedup_service, "_same_source_external_row", return_value=None),
            patch.object(dedup_service, "_resolved_same_source_external_row", return_value=None),
            patch.object(dedup_service, "_create_new_canonical_row", return_value=sentinel),
        ):
            row, outcome = dedup_service._upsert_dedup_inner(
                canonical=self._CANONICAL,
                source="glitchtip",
                external_id="gt-lock-probe",
                fingerprint="glitchtip-fp-lock",
                title="Lock probe",
                description="desc",
                affected_files=[],
                severity="medium",
                priority_score=0.5,
                occurrence_count=1,
            )

        self.assertIs(row, sentinel)
        self.assertEqual(outcome, "created")


class InternalPickerTests(TestCase):
    def setUp(self):
        AutoIssue.objects.all().delete()
        ErrorLog.objects.filter(source=ErrorLog.SOURCE_INTERNAL).delete()

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
