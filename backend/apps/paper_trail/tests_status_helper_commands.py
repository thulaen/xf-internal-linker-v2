"""TDD tests for mark_paper_trail_stale + link_paper_trail_supersedes."""

from __future__ import annotations

from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.tests_helpers import valid_paper_trail_defaults


def _make(**overrides) -> PaperTrailEntry:
    defaults = valid_paper_trail_defaults(
        category=PaperTrailEntry.CATEGORY_OTHER,
        title="status-helper fixture",
        abstract=(
            "Given the status-helper command tests need a row, "
            "When _make() constructs one, "
            "Then it passes BDD validation."
        ),
    )
    defaults.update(overrides)
    return PaperTrailEntry.objects.create(**defaults)


class MarkStaleCommandTests(TestCase):
    def test_marks_entry_stale_with_reason(self) -> None:
        entry = _make()
        out = StringIO()
        call_command(
            "mark_paper_trail_stale",
            "--id", str(entry.pk),
            "--reason", "Affected file was deleted on 2026-05-12.",
            "--agent", "claude",
            stdout=out,
        )
        entry.refresh_from_db()
        self.assertEqual(entry.status, PaperTrailEntry.STATUS_STALE)
        self.assertIn("[PAPER TRAIL STALE:", out.getvalue())
        self.assertIn("2026-05-12", entry.suppression_reason)
        self.assertEqual(entry.suppression_approver, "claude")

    def test_rejects_empty_reason(self) -> None:
        entry = _make()
        with self.assertRaises(CommandError) as cm:
            call_command(
                "mark_paper_trail_stale",
                "--id", str(entry.pk),
                "--reason", "   ",
                stdout=StringIO(),
            )
        self.assertIn("--reason", str(cm.exception))

    def test_rejects_missing_id(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "mark_paper_trail_stale",
                "--id", "999999",
                "--reason", "x",
                stdout=StringIO(),
            )

    def test_noop_when_already_stale(self) -> None:
        entry = _make()
        entry.status = PaperTrailEntry.STATUS_STALE
        entry.suppression_reason = "previously marked stale"
        entry.save()
        out = StringIO()
        call_command(
            "mark_paper_trail_stale",
            "--id", str(entry.pk),
            "--reason", "trying again",
            stdout=out,
        )
        self.assertIn("STALE NO-OP", out.getvalue())


class LinkSupersedesCommandTests(TestCase):
    def test_links_old_to_new(self) -> None:
        old = _make(title="old A")
        new = _make(title="new B")
        out = StringIO()
        call_command(
            "link_paper_trail_supersedes",
            "--new-id", str(new.pk),
            "--old-id", str(old.pk),
            stdout=out,
        )
        old.refresh_from_db()
        self.assertEqual(old.status, PaperTrailEntry.STATUS_SUPERSEDED)
        self.assertEqual(old.superseded_by_id, new.pk)
        self.assertIn("SUPERSEDED", out.getvalue())

    def test_links_multiple_old_entries(self) -> None:
        old_a = _make(title="old A")
        old_b = _make(title="old B")
        new = _make(title="consolidated new")
        call_command(
            "link_paper_trail_supersedes",
            "--new-id", str(new.pk),
            "--old-id", str(old_a.pk),
            "--old-id", str(old_b.pk),
            stdout=StringIO(),
        )
        old_a.refresh_from_db()
        old_b.refresh_from_db()
        self.assertEqual(old_a.superseded_by_id, new.pk)
        self.assertEqual(old_b.superseded_by_id, new.pk)

    def test_rejects_self_supersede(self) -> None:
        entry = _make()
        with self.assertRaises(CommandError) as cm:
            call_command(
                "link_paper_trail_supersedes",
                "--new-id", str(entry.pk),
                "--old-id", str(entry.pk),
                stdout=StringIO(),
            )
        self.assertIn("cannot supersede itself", str(cm.exception))

    def test_rejects_missing_new_id(self) -> None:
        old = _make()
        with self.assertRaises(CommandError):
            call_command(
                "link_paper_trail_supersedes",
                "--new-id", "999999",
                "--old-id", str(old.pk),
                stdout=StringIO(),
            )

    def test_noop_when_old_already_superseded(self) -> None:
        old = _make(title="old A")
        first_new = _make(title="first new")
        second_new = _make(title="second new")
        call_command(
            "link_paper_trail_supersedes",
            "--new-id", str(first_new.pk),
            "--old-id", str(old.pk),
            stdout=StringIO(),
        )
        out = StringIO()
        call_command(
            "link_paper_trail_supersedes",
            "--new-id", str(second_new.pk),
            "--old-id", str(old.pk),
            stdout=out,
        )
        self.assertIn("SUPERSEDE NO-OP", out.getvalue())
