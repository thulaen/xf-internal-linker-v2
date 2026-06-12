"""Extra model-level tests for AutoIssue.

Covers:
- Bug 5 fix: resolved_at must be auto-set when status transitions to RESOLVED.
- Bug 6 fix: priority_score and spam_score must be validated to [0, 1].
- __str__ format.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


def _make_issue(**kwargs) -> AutoIssue:
    defaults = dict(
        source=AutoIssue.SOURCE_AGENT,
        external_id="models-extra-test-1",
        fingerprint="models-extra-fp-1",
        title="Test issue for model validators",
        severity=AutoIssue.SEVERITY_MEDIUM,
        status=AutoIssue.STATUS_OPEN,
    )
    defaults.update(kwargs)
    return AutoIssue(**defaults)


# ── score field validators (Bug 6) ────────────────────────────────────────


class PriorityScoreValidatorTests(TestCase):
    def test_valid_priority_score_passes(self):
        issue = _make_issue(priority_score=0.5)
        issue.full_clean()  # must not raise

    def test_zero_priority_score_passes(self):
        issue = _make_issue(priority_score=0.0)
        issue.full_clean()

    def test_one_priority_score_passes(self):
        issue = _make_issue(priority_score=1.0)
        issue.full_clean()

    def test_priority_score_above_one_fails_validation(self):
        """Bug 6 fix: priority_score > 1.0 must raise ValidationError."""
        issue = _make_issue(priority_score=1.5)
        with self.assertRaises(ValidationError):
            issue.full_clean()

    def test_priority_score_below_zero_fails_validation(self):
        """Bug 6 fix: priority_score < 0.0 must raise ValidationError."""
        issue = _make_issue(priority_score=-0.1)
        with self.assertRaises(ValidationError):
            issue.full_clean()

    def test_priority_score_far_above_one_fails(self):
        issue = _make_issue(priority_score=99.9)
        with self.assertRaises(ValidationError):
            issue.full_clean()


class SpamScoreValidatorTests(TestCase):
    def test_null_spam_score_passes(self):
        issue = _make_issue(spam_score=None)
        issue.full_clean()

    def test_valid_spam_score_passes(self):
        issue = _make_issue(spam_score=0.75)
        issue.full_clean()

    def test_zero_spam_score_passes(self):
        issue = _make_issue(spam_score=0.0)
        issue.full_clean()

    def test_one_spam_score_passes(self):
        issue = _make_issue(spam_score=1.0)
        issue.full_clean()

    def test_spam_score_above_one_fails_validation(self):
        """Bug 6 fix: spam_score > 1.0 must raise ValidationError."""
        issue = _make_issue(spam_score=1.1)
        with self.assertRaises(ValidationError):
            issue.full_clean()

    def test_spam_score_below_zero_fails_validation(self):
        """Bug 6 fix: spam_score < 0.0 must raise ValidationError."""
        issue = _make_issue(spam_score=-0.5)
        with self.assertRaises(ValidationError):
            issue.full_clean()


# ── resolved_at auto-set (Bug 5) ──────────────────────────────────────────


class ResolvedAtAutoSetTests(TestCase):
    def test_resolved_at_auto_set_on_status_change(self):
        """Bug 5 fix: save() must set resolved_at when status transitions to RESOLVED."""
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="resolved-at-test-1",
            fingerprint="resolved-at-fp-1",
            title="Auto resolved_at test",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_OPEN,
        )
        self.assertIsNone(issue.resolved_at)
        issue.status = AutoIssue.STATUS_RESOLVED
        issue.save()
        issue.refresh_from_db()
        self.assertIsNotNone(issue.resolved_at)

    def test_resolved_at_not_overwritten_if_already_set(self):
        explicit_time = timezone.now()
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="resolved-at-test-2",
            fingerprint="resolved-at-fp-2",
            title="Explicit resolved_at test",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_OPEN,
        )
        issue.status = AutoIssue.STATUS_RESOLVED
        issue.resolved_at = explicit_time
        issue.save()
        issue.refresh_from_db()
        # Must not replace the explicit time with a new timezone.now() call.
        delta = abs((issue.resolved_at - explicit_time).total_seconds())
        self.assertLess(delta, 1.0)

    def test_resolved_at_not_set_for_other_statuses(self):
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="resolved-at-test-3",
            fingerprint="resolved-at-fp-3",
            title="Picked status test",
            severity=AutoIssue.SEVERITY_LOW,
            status=AutoIssue.STATUS_OPEN,
        )
        issue.status = AutoIssue.STATUS_PICKED
        issue.save()
        issue.refresh_from_db()
        self.assertIsNone(issue.resolved_at)

    def test_resolved_at_set_correctly_even_with_update_fields(self):
        """When save(update_fields=[...]) is used, resolved_at is included automatically."""
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="resolved-at-test-4",
            fingerprint="resolved-at-fp-4",
            title="Update fields test",
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_OPEN,
        )
        issue.status = AutoIssue.STATUS_RESOLVED
        issue.save(update_fields=["status"])
        issue.refresh_from_db()
        self.assertIsNotNone(issue.resolved_at)


# ── __str__ ───────────────────────────────────────────────────────────────


class AutoIssueStrTests(TestCase):
    def test_str_contains_source_severity_and_title(self):
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_GLITCHTIP,
            external_id="str-test-1",
            fingerprint="str-fp-1",
            title="ValueError in views.py line 42",
            severity=AutoIssue.SEVERITY_HIGH,
            status=AutoIssue.STATUS_OPEN,
        )
        result = str(issue)
        self.assertIn("glitchtip", result)
        self.assertIn("high", result)
        self.assertIn("ValueError in views.py", result)

    def test_str_truncates_long_title(self):
        long_title = "X" * 200
        issue = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id="str-test-2",
            fingerprint="str-fp-2",
            title=long_title,
            severity=AutoIssue.SEVERITY_LOW,
            status=AutoIssue.STATUS_OPEN,
        )
        result = str(issue)
        self.assertLessEqual(len(result), 100)


# ── Field checks for migrations ───────────────────────────────────────────


class MigrationFieldTests(TestCase):
    def test_model_has_build_failure_evidence(self):
        """Fix for AutoIssue #21124 (0021_build_failure_evidence.py)."""
        self.assertTrue(hasattr(AutoIssue, "build_failure_evidence"))

    def test_model_has_codeql_evidence(self):
        """Fix for AutoIssue #21122 (0020_codeql_finding_evidence.py)."""
        self.assertTrue(hasattr(AutoIssue, "codeql_evidence"))

    def test_model_has_priority_score(self):
        """Fix for AutoIssue #21120 (0019_alter_autoissue_priority_score_and_more.py)."""
        self.assertTrue(hasattr(AutoIssue, "priority_score"))
