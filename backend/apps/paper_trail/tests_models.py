"""TDD tests for PaperTrailEntry model — written BEFORE the model code.

Covers:
- Minimal entry creation with auto-computed fingerprints
- Word-count cap on abstract (600 words)
- Lesson-format validation on resolve
- Wontfix requires suppression_reason
- Active unique constraint (category, fingerprint) for non-terminal status
- Resolved entries do not block new entries with same fingerprint
- History audit log append
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry


def _make_minimal(**overrides) -> PaperTrailEntry:
    defaults = {
        "category": PaperTrailEntry.CATEGORY_OTHER,
        "title": "Test deferral",
        "abstract": (
            "Given a test wants to construct a minimal paper-trail entry, "
            "When _make_minimal() is called, "
            "Then a saveable PaperTrailEntry with BDD-shaped abstract is returned."
        ),
        "deferred_by": "test-agent",
        "risk_on_inaction": "Test-only entry; no real risk.",
        "acceptance_criteria": "Test passes when the row is saved.",
    }
    defaults.update(overrides)
    return PaperTrailEntry.objects.create(**defaults)


class FingerprintTests(TestCase):
    def test_fingerprint_auto_computed_on_save(self) -> None:
        entry = _make_minimal()
        self.assertEqual(len(entry.fingerprint), 16)
        self.assertEqual(len(entry.canonical_fingerprint), 16)

    def test_same_title_and_category_yields_same_fingerprint(self) -> None:
        a = _make_minimal(title="Same title")
        with transaction.atomic():
            # Re-creation with same key would violate the constraint;
            # we resolve A first then re-create to compare fingerprints.
            a.status = PaperTrailEntry.STATUS_RESOLVED
            a.resolved_at = timezone.now()
            a.resolution_lessons = "Trap: x. Fix shape: y."
            a.save()
        b = _make_minimal(title="Same title")
        self.assertEqual(a.fingerprint, b.fingerprint)

    def test_different_title_yields_different_fingerprint(self) -> None:
        a = _make_minimal(title="First title")
        b = _make_minimal(title="Second title")
        self.assertNotEqual(a.fingerprint, b.fingerprint)

    def test_linked_autoissue_affects_fingerprint(self) -> None:
        a = _make_minimal(title="Same title", linked_autoissue_id=100)
        b = _make_minimal(title="Same title", linked_autoissue_id=200)
        self.assertNotEqual(a.fingerprint, b.fingerprint)


def _bdd_filler(n_words: int) -> str:
    """Build a BDD-shaped filler abstract of approximately `n_words` words."""
    header = "Given a test wants to fill the abstract, When _bdd_filler builds the text, Then it returns a BDD-shaped string."
    header_words = len(header.split())
    pad_words = max(0, n_words - header_words)
    pad = " ".join("word" for _ in range(pad_words))
    return f"{header} {pad}".strip()


class AbstractCapTests(TestCase):
    def test_abstract_under_1200_words_accepted(self) -> None:
        abstract = _bdd_filler(1199)
        entry = _make_minimal(abstract=abstract)
        self.assertLessEqual(len(entry.abstract.split()), 1200)

    def test_abstract_exactly_1200_words_accepted(self) -> None:
        abstract = _bdd_filler(1200)
        entry = _make_minimal(abstract=abstract)
        self.assertEqual(len(entry.abstract.split()), 1200)

    def test_abstract_over_1200_words_rejected(self) -> None:
        abstract = _bdd_filler(1201)
        with self.assertRaises(ValidationError) as cm:
            _make_minimal(abstract=abstract)
        self.assertIn("1200", str(cm.exception))


class BDDFormatTests(TestCase):
    def test_abstract_with_given_when_then_accepted(self) -> None:
        entry = _make_minimal(
            abstract=(
                "Given a deferral needs filing, "
                "When the agent runs defer_work with all three BDD sections, "
                "Then the model save passes validation."
            ),
        )
        self.assertTrue(entry.pk)

    def test_abstract_missing_given_rejected_on_new_entry(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            _make_minimal(
                abstract="When something happens Then something else follows.",
            )
        self.assertIn("Given", str(cm.exception))

    def test_abstract_missing_when_rejected_on_new_entry(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            _make_minimal(
                abstract="Given a context Then a result.",
            )
        self.assertIn("When", str(cm.exception))

    def test_abstract_missing_then_rejected_on_new_entry(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            _make_minimal(
                abstract="Given a context When an action occurs.",
            )
        self.assertIn("Then", str(cm.exception))

    def test_existing_entry_update_skips_bdd_validation(self) -> None:
        """Grandfather clause: existing rows being status-changed do not
        re-trigger BDD validation. Only new rows (self._state.adding) do.
        """
        entry = _make_minimal()  # default abstract already BDD-shaped
        # Bypass the model save() validator to install a non-BDD abstract
        # the way a pre-2026-05-16 row would look.
        PaperTrailEntry.objects.filter(pk=entry.pk).update(
            abstract="Old narrative prose without any BDD shape."
        )
        entry.refresh_from_db()
        # Status-change save MUST NOT raise on the legacy abstract.
        entry.status = PaperTrailEntry.STATUS_IN_PROGRESS
        entry.save()  # would raise if BDD validation re-fired


class ResolutionLessonTests(TestCase):
    def test_resolved_requires_two_part_lesson(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_RESOLVED
        entry.resolved_at = timezone.now()
        entry.resolution_lessons = ""
        with self.assertRaises(ValidationError):
            entry.save()

    def test_resolved_lesson_missing_trap_rejected(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_RESOLVED
        entry.resolved_at = timezone.now()
        entry.resolution_lessons = "Fix shape: did X."
        with self.assertRaises(ValidationError):
            entry.save()

    def test_resolved_lesson_missing_fix_shape_rejected(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_RESOLVED
        entry.resolved_at = timezone.now()
        entry.resolution_lessons = "Trap: y was tricky."
        with self.assertRaises(ValidationError):
            entry.save()

    def test_resolved_with_two_part_lesson_succeeds(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_RESOLVED
        entry.resolved_at = timezone.now()
        entry.resolution_lessons = "Trap: y was tricky. Fix shape: did X."
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_RESOLVED)


class WontfixSuppressionTests(TestCase):
    def test_wontfix_without_reason_rejected(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_WONTFIX
        entry.suppression_reason = ""
        with self.assertRaises(ValidationError):
            entry.save()

    def test_wontfix_with_reason_succeeds(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_WONTFIX
        entry.suppression_reason = "Out of scope — superseded by new approach."
        entry.suppression_approver = "operator"
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_WONTFIX)


class UniqueConstraintTests(TestCase):
    def test_two_active_same_category_same_fingerprint_rejected(self) -> None:
        _make_minimal(title="Conflict")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                # Bypass save-time auto-compute to force a collision.
                PaperTrailEntry.objects.create(
                    category=PaperTrailEntry.CATEGORY_OTHER,
                    title="Conflict",
                    abstract=(
                        "Given the unique-constraint test needs a second "
                        "row with the same title, "
                        "When the second create attempts, "
                        "Then the DB raises IntegrityError before the "
                        "abstract content matters."
                    ),
                    deferred_by="test-agent",
                    risk_on_inaction="Test only.",
                    acceptance_criteria="Test passes.",
                )

    def test_resolved_does_not_block_new_active(self) -> None:
        a = _make_minimal(title="Same title")
        a.status = PaperTrailEntry.STATUS_RESOLVED
        a.resolved_at = timezone.now()
        a.resolution_lessons = "Trap: x. Fix shape: y."
        a.save()
        b = _make_minimal(title="Same title")
        self.assertNotEqual(a.id, b.id)
        self.assertEqual(b.status, PaperTrailEntry.STATUS_OPEN)


class HistoryAuditLogTests(TestCase):
    def test_creation_appends_first_history_entry(self) -> None:
        entry = _make_minimal()
        self.assertEqual(len(entry.history), 1)
        self.assertEqual(entry.history[0]["action"], "created")
        self.assertEqual(entry.history[0]["by"], "test-agent")
        self.assertIn("at", entry.history[0])

    def test_status_change_appends_history_entry(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_IN_PROGRESS
        entry.save()
        self.assertEqual(len(entry.history), 2)
        self.assertEqual(entry.history[-1]["action"], "status:in_progress")


class RequiredFieldTests(TestCase):
    """2026-05-16: risk_on_inaction and acceptance_criteria are required
    on NEW rows. Existing rows grandfathered via self._state.adding.
    """

    def test_missing_risk_on_inaction_rejected_on_new(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            _make_minimal(risk_on_inaction="")
        self.assertIn("risk_on_inaction", str(cm.exception))

    def test_missing_acceptance_criteria_rejected_on_new(self) -> None:
        with self.assertRaises(ValidationError) as cm:
            _make_minimal(acceptance_criteria="")
        self.assertIn("acceptance_criteria", str(cm.exception))

    def test_existing_entry_update_skips_required_field_validation(self) -> None:
        """Status changes on grandfathered rows must not retro-trigger
        the required-field check.
        """
        entry = _make_minimal()
        # Wipe the required fields via raw update to simulate a pre-2026-05-16 row.
        PaperTrailEntry.objects.filter(pk=entry.pk).update(
            risk_on_inaction="",
            acceptance_criteria="",
        )
        entry.refresh_from_db()
        entry.status = PaperTrailEntry.STATUS_IN_PROGRESS
        entry.save()  # would raise if required-field check re-fired


class NewStatusTests(TestCase):
    """2026-05-16: 5 new statuses (blocked, deferred, stale, superseded, rejected)."""

    def test_blocked_requires_blockers(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_BLOCKED
        entry.blockers = []
        with self.assertRaises(ValidationError) as cm:
            entry.save()
        self.assertIn("blockers", str(cm.exception))

    def test_blocked_with_blockers_succeeds(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_BLOCKED
        entry.blockers = ["waiting on Django 5.3 release"]
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_BLOCKED)

    def test_stale_requires_suppression_reason(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_STALE
        entry.suppression_reason = ""
        with self.assertRaises(ValidationError):
            entry.save()

    def test_stale_with_reason_succeeds(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_STALE
        entry.suppression_reason = "Code area was refactored away on 2026-05-12."
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_STALE)

    def test_superseded_requires_superseded_by(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_SUPERSEDED
        with self.assertRaises(ValidationError) as cm:
            entry.save()
        self.assertIn("superseded_by", str(cm.exception))

    def test_superseded_with_link_succeeds(self) -> None:
        old = _make_minimal(title="old")
        new = _make_minimal(title="new")
        old.status = PaperTrailEntry.STATUS_SUPERSEDED
        old.superseded_by = new
        old.save()
        old.refresh_from_db()
        self.assertEqual(old.status, PaperTrailEntry.STATUS_SUPERSEDED)
        self.assertEqual(old.superseded_by_id, new.pk)

    def test_rejected_requires_suppression_reason(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_REJECTED
        entry.suppression_reason = ""
        with self.assertRaises(ValidationError):
            entry.save()

    def test_rejected_with_reason_succeeds(self) -> None:
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_REJECTED
        entry.suppression_reason = "Approach was tried and abandoned."
        entry.suppression_approver = "operator"
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_REJECTED)

    def test_deferred_status_does_not_block_resolution(self) -> None:
        """deferred is an active status — it can transition to resolved later."""
        entry = _make_minimal()
        entry.status = PaperTrailEntry.STATUS_DEFERRED
        entry.save()
        entry.refresh_from_db()
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_DEFERRED)
        entry.status = PaperTrailEntry.STATUS_RESOLVED
        entry.resolved_at = timezone.now()
        entry.resolution_lessons = "Trap: x. Fix shape: y."
        entry.save()
