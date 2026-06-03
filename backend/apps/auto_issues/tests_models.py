"""Convention-named SimpleTestCase coverage for apps/auto_issues/models.py.

The mutation gate discovers ONLY this exact filename (``tests_models.py`` next
to ``models.py``).  These tests pin two diff-scoped behaviours without touching
the real database:

1. ``AutoIssue.save()`` auto-sets ``resolved_at`` exactly when the status is
   RESOLVED and ``resolved_at`` is still None, and threads ``resolved_at`` into
   ``update_fields`` when that kwarg was passed.  The persistence call
   (``super().save``) is mocked so no row is written.
2. The ``priority_score`` and ``spam_score`` validators bound the value to the
   inclusive range [0.0, 1.0].  The exact boundary literals are asserted so a
   mutant that shifts 0.0 → 1 or 1.0 → 2 (or drops a validator) is killed.
"""

from __future__ import annotations

from unittest.mock import patch

from django.core.validators import MaxValueValidator, MinValueValidator
from django.test import SimpleTestCase

from apps.auto_issues.models import AutoIssue


def _field_bounds(field_name: str) -> tuple[float, float]:
    """Return (min_limit, max_limit) read off the field's validators."""
    field = AutoIssue._meta.get_field(field_name)
    min_limit = next(
        v.limit_value for v in field.validators if isinstance(v, MinValueValidator)
    )
    max_limit = next(
        v.limit_value for v in field.validators if isinstance(v, MaxValueValidator)
    )
    return min_limit, max_limit


class ScoreValidatorBoundsTests(SimpleTestCase):
    """priority_score and spam_score are bounded to the inclusive range [0, 1]."""

    def test_priority_score_min_bound_is_exactly_zero(self) -> None:
        min_limit, _ = _field_bounds("priority_score")
        self.assertEqual(min_limit, 0.0)

    def test_priority_score_max_bound_is_exactly_one(self) -> None:
        _, max_limit = _field_bounds("priority_score")
        self.assertEqual(max_limit, 1.0)

    def test_spam_score_min_bound_is_exactly_zero(self) -> None:
        min_limit, _ = _field_bounds("spam_score")
        self.assertEqual(min_limit, 0.0)

    def test_spam_score_max_bound_is_exactly_one(self) -> None:
        _, max_limit = _field_bounds("spam_score")
        self.assertEqual(max_limit, 1.0)

    def test_priority_score_validator_accepts_exact_boundaries(self) -> None:
        field = AutoIssue._meta.get_field("priority_score")
        for validator in field.validators:
            validator(0.0)  # lower bound inclusive — must not raise
            validator(1.0)  # upper bound inclusive — must not raise

    def test_spam_score_validator_accepts_exact_boundaries(self) -> None:
        field = AutoIssue._meta.get_field("spam_score")
        for validator in field.validators:
            validator(0.0)
            validator(1.0)


class ResolvedAtSaveHookTests(SimpleTestCase):
    """save() sets resolved_at only on the RESOLVED transition, DB-free.

    ``django.db.models.Model.save`` is patched to a no-op so the hook logic
    runs without writing a row. Each assertion pins the exact branch so a
    mutant that flips the status compare or the ``is None`` guard is killed.
    """

    def _save(self, issue: AutoIssue, **kwargs) -> dict:
        captured: dict = {}

        def fake_super_save(self_inner, *a, **kw):
            captured["update_fields"] = kw.get("update_fields")

        with patch("django.db.models.Model.save", fake_super_save):
            issue.save(**kwargs)
        return captured

    def test_resolved_at_set_when_status_resolved_and_unset(self) -> None:
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            external_id="hook-1",
            title="t",
            status=AutoIssue.STATUS_RESOLVED,
        )
        self.assertIsNone(issue.resolved_at)
        self._save(issue)
        self.assertIsNotNone(issue.resolved_at)

    def test_resolved_at_not_set_for_non_resolved_status(self) -> None:
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            external_id="hook-2",
            title="t",
            status=AutoIssue.STATUS_PICKED,
        )
        self._save(issue)
        self.assertIsNone(issue.resolved_at)

    def test_resolved_at_not_overwritten_when_already_set(self) -> None:
        from django.utils import timezone

        explicit = timezone.now()
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            external_id="hook-3",
            title="t",
            status=AutoIssue.STATUS_RESOLVED,
            resolved_at=explicit,
        )
        self._save(issue)
        self.assertIs(issue.resolved_at, explicit)

    def test_update_fields_gets_resolved_at_appended(self) -> None:
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            external_id="hook-4",
            title="t",
            status=AutoIssue.STATUS_RESOLVED,
        )
        captured = self._save(issue, update_fields=["status"])
        self.assertIn("resolved_at", captured["update_fields"])
        self.assertIn("status", captured["update_fields"])

    def test_update_fields_not_duplicated_when_already_present(self) -> None:
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            external_id="hook-5",
            title="t",
            status=AutoIssue.STATUS_RESOLVED,
        )
        captured = self._save(issue, update_fields=["status", "resolved_at"])
        self.assertEqual(captured["update_fields"].count("resolved_at"), 1)

    def test_update_fields_untouched_for_non_resolved_status(self) -> None:
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            external_id="hook-6",
            title="t",
            status=AutoIssue.STATUS_OPEN,
        )
        captured = self._save(issue, update_fields=["status"])
        self.assertEqual(captured["update_fields"], ["status"])


class AutoIssueStrTests(SimpleTestCase):
    """__str__ keeps the [source/severity] prefix and caps at 100 chars."""

    def test_str_contains_source_and_severity_and_title(self) -> None:
        issue = AutoIssue(
            source=AutoIssue.SOURCE_GLITCHTIP,
            severity=AutoIssue.SEVERITY_HIGH,
            title="ValueError in views",
        )
        result = str(issue)
        self.assertEqual(result, "[glitchtip/high] ValueError in views")

    def test_str_caps_total_length_at_100(self) -> None:
        issue = AutoIssue(
            source=AutoIssue.SOURCE_AGENT,
            severity=AutoIssue.SEVERITY_LOW,
            title="X" * 300,
        )
        self.assertEqual(len(str(issue)), 100)
