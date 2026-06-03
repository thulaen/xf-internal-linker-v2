"""TDD tests for verify_paper_trail_quota command."""

from __future__ import annotations

from datetime import timedelta
from io import StringIO

from django.core.management import CommandError, call_command
from django.test import TestCase
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.tests_helpers import valid_paper_trail_defaults


def _resolved(
    title: str, *, resolved_at, lessons="Trap: x. Fix shape: y."
) -> PaperTrailEntry:
    entry = PaperTrailEntry.objects.create(
        **valid_paper_trail_defaults(
            category=PaperTrailEntry.CATEGORY_OTHER,
            title=title,
            abstract=(
                "Given the verify_quota tests need a paper-trail row, "
                "When _resolved() constructs one, "
                "Then it passes BDD validation."
            ),
        )
    )
    entry.status = PaperTrailEntry.STATUS_RESOLVED
    entry.resolved_at = resolved_at
    entry.resolved_by = "claude"
    entry.resolution_lessons = lessons
    entry.save()
    return entry


class VerifyQuotaTests(TestCase):
    def test_passes_with_10_resolved(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(10)]
        out = StringIO()
        call_command(
            "verify_paper_trail_quota",
            "--ids",
            *[str(i) for i in ids],
            stdout=out,
        )
        self.assertIn("QUOTA VERIFIED", out.getvalue())

    def test_fails_with_9(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(9)]
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(i) for i in ids],
                stdout=StringIO(),
            )

    def test_fails_on_duplicate_ids(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(9)]
        ids.append(ids[0])  # 10 IDs but one duplicate
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(i) for i in ids],
                stdout=StringIO(),
            )

    def test_fails_on_duplicate_canonical_work(self) -> None:
        now = timezone.now()
        entries = [_resolved(f"t{i}", resolved_at=now) for i in range(10)]
        PaperTrailEntry.objects.filter(pk__in=[entries[0].pk, entries[1].pk]).update(
            canonical_fingerprint="same-paper-work"
        )
        with self.assertRaisesMessage(CommandError, "Duplicate Paper Trail work"):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(entry.pk) for entry in entries],
                stdout=StringIO(),
            )

    def test_fails_when_resolved_before_cutoff(self) -> None:
        old = timezone.now() - timedelta(days=3)
        ids = [_resolved(f"t{i}", resolved_at=old).pk for i in range(10)]
        cutoff = (timezone.now() - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(i) for i in ids],
                "--resolved-after",
                cutoff,
                stdout=StringIO(),
            )

    def test_fails_on_missing_lesson_tokens(self) -> None:
        """Model save() rejects malformed lessons, but the verify gate is
        the FINAL check before commit. The gate must independently catch
        rows that bypassed validation (raw SQL, fixture load, etc.).
        Use queryset.update() to bypass save() so we can test the gate.
        """
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(10)]
        # Bypass save() to simulate a malformed row.
        PaperTrailEntry.objects.filter(pk__in=ids).update(
            resolution_lessons="Trap: only — no fix-shape part"
        )
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(i) for i in ids],
                stdout=StringIO(),
            )

    def test_invalid_resolved_after_fails_plainly(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(10)]
        with self.assertRaisesMessage(CommandError, "Could not parse"):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(i) for i in ids],
                "--resolved-after",
                "not-a-date",
                stdout=StringIO(),
            )

    def test_missing_entry_fails(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(9)]
        ids.append(999_999)
        with self.assertRaisesMessage(CommandError, "PaperTrailEntry not found"):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(i) for i in ids],
                stdout=StringIO(),
            )

    def test_unresolved_entry_fails(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(10)]
        PaperTrailEntry.objects.filter(pk=ids[0]).update(
            status=PaperTrailEntry.STATUS_OPEN
        )
        with self.assertRaisesMessage(CommandError, "Not resolved"):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(i) for i in ids],
                stdout=StringIO(),
            )

    def test_missing_resolved_timestamp_fails(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"t{i}", resolved_at=now).pk for i in range(10)]
        PaperTrailEntry.objects.filter(pk=ids[0]).update(resolved_at=None)
        with self.assertRaisesMessage(CommandError, "Missing resolved_at"):
            call_command(
                "verify_paper_trail_quota",
                "--ids",
                *[str(i) for i in ids],
                stdout=StringIO(),
            )


class SessionTypeScalingTests(TestCase):
    """Tests for --session-type quota scaling (Increment 0).

    Given a session with a non-feature session type,
    When verify_paper_trail_quota is called with that session type,
    Then the required number of IDs matches the scaled quota.
    """

    def test_docs_passes_immediately_with_zero_ids(self) -> None:
        out = StringIO()
        call_command(
            "verify_paper_trail_quota",
            "--session-type", "docs",
            stdout=out,
        )
        self.assertIn("docs", out.getvalue().lower())
        self.assertIn("no quota required", out.getvalue().lower())

    def test_reconciliation_passes_with_three_ids(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"r{i}", resolved_at=now).pk for i in range(3)]
        out = StringIO()
        call_command(
            "verify_paper_trail_quota",
            "--ids", *[str(i) for i in ids],
            "--session-type", "reconciliation",
            stdout=out,
        )
        self.assertIn("QUOTA VERIFIED", out.getvalue())
        self.assertIn("3 resolved", out.getvalue())

    def test_reconciliation_fails_with_two_ids(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"r{i}", resolved_at=now).pk for i in range(2)]
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids", *[str(i) for i in ids],
                "--session-type", "reconciliation",
                stdout=StringIO(),
            )

    def test_infrastructure_passes_with_five_ids(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"i{n}", resolved_at=now).pk for n in range(5)]
        out = StringIO()
        call_command(
            "verify_paper_trail_quota",
            "--ids", *[str(i) for i in ids],
            "--session-type", "infrastructure",
            stdout=out,
        )
        self.assertIn("QUOTA VERIFIED", out.getvalue())
        self.assertIn("5 resolved", out.getvalue())

    def test_infrastructure_fails_with_four_ids(self) -> None:
        now = timezone.now()
        ids = [_resolved(f"i{n}", resolved_at=now).pk for n in range(4)]
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids", *[str(i) for i in ids],
                "--session-type", "infrastructure",
                stdout=StringIO(),
            )

    def test_feature_still_requires_ten(self) -> None:
        now = timezone.now()
        ids_9 = [_resolved(f"f{n}", resolved_at=now).pk for n in range(9)]
        with self.assertRaises(CommandError):
            call_command(
                "verify_paper_trail_quota",
                "--ids", *[str(i) for i in ids_9],
                "--session-type", "feature",
                stdout=StringIO(),
            )


class HardModeTests(TestCase):
    """Tests for the --hard auto-pick path (no --ids supplied).

    Given a session that omits --ids,
    When --hard auto-selects resolved rows from the database,
    Then the command verifies exactly the session-type quota or fails
    with the exact short-count message. These pin the new --hard branch
    and the _hard_mode_ids ordering/limit so the diff-scoped mutation
    gate cannot keep a survivor on the changed executable lines.
    """

    def test_no_ids_without_hard_raises_exact_message(self) -> None:
        # The False branch of ``if not opts.get("hard")`` — omitting both
        # --ids and --hard must raise the exact guidance string.
        with self.assertRaisesMessage(
            CommandError, "--ids is required unless --hard is used."
        ):
            call_command("verify_paper_trail_quota", stdout=StringIO())

    def test_hard_passes_when_exactly_quota_resolved_rows_exist(self) -> None:
        # reconciliation quota == 3; create exactly 3 resolved rows so the
        # auto-pick returns 3 and the command verifies. Proves _hard_mode_ids
        # selects resolved rows and the len()==quota check passes.
        now = timezone.now()
        for n in range(3):
            _resolved(f"h{n}", resolved_at=now)
        out = StringIO()
        call_command(
            "verify_paper_trail_quota",
            "--hard",
            "--session-type", "reconciliation",
            stdout=out,
        )
        self.assertIn("QUOTA VERIFIED", out.getvalue())
        self.assertIn("3 resolved", out.getvalue())

    def test_hard_shortfall_raises_exact_short_count(self) -> None:
        # Only 2 resolved rows but reconciliation needs 3: the short-count
        # branch must fire with the exact "2 of 3 resolved (1 short)" wording.
        now = timezone.now()
        for n in range(2):
            _resolved(f"s{n}", resolved_at=now)
        with self.assertRaisesMessage(
            CommandError, "paper-trail: 2 of 3 resolved (1 short)"
        ):
            call_command(
                "verify_paper_trail_quota",
                "--hard",
                "--session-type", "reconciliation",
                stdout=StringIO(),
            )

    def test_hard_respects_resolved_after_cutoff(self) -> None:
        # Rows resolved BEFORE the cutoff are excluded by _hard_mode_ids'
        # ``resolved_at__gt=cutoff`` filter, so 2 old + 1 new == 1 picked,
        # which is short of the reconciliation quota of 3.
        now = timezone.now()
        old = now - timedelta(days=3)
        for n in range(2):
            _resolved(f"old{n}", resolved_at=old)
        _resolved("new0", resolved_at=now)
        cutoff = (now - timedelta(days=1)).strftime("%Y-%m-%d %H:%M")
        with self.assertRaisesMessage(
            CommandError, "paper-trail: 1 of 3 resolved (2 short)"
        ):
            call_command(
                "verify_paper_trail_quota",
                "--hard",
                "--resolved-after", cutoff,
                "--session-type", "reconciliation",
                stdout=StringIO(),
            )
