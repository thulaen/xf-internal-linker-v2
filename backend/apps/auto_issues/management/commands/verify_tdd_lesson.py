"""manage.py verify_tdd_lesson --id <N> [--id <M>] — hook-side validator.

Called by `.githooks/check-tdd-strict.py` to confirm every
`lesson_autoissue=#N` referenced in `[TDD CYCLE STRICT: ...]` markers
resolves to a real, properly-shaped lesson row in the live database.

Exit codes:
  0 — the row exists, has category='tdd_lesson', status='resolved', and a
      `Trap: ... Fix shape: ...` lessons_learned payload.
  2 — any of the above is false; stderr has a plain-English Rule-F message.

Spec: docs/TDD-STRICT-RULE.md
"""

from __future__ import annotations

import sys

from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssue


class Command(BaseCommand):
    help = "Verify lesson AutoIssue ids passed by the strict-TDD hook."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--id", type=int, action="append", dest="ids", required=True,
            help="AutoIssue id from a [TDD CYCLE STRICT:] marker. Repeatable.",
        )

    def handle(self, *args, **opts) -> None:
        issue_ids: list[int] = list(dict.fromkeys(opts["ids"]))
        for issue_id in issue_ids:
            self._verify_one(issue_id)

    def _verify_one(self, issue_id: int) -> None:
        try:
            ai = AutoIssue.objects.select_related("category").get(pk=issue_id)
        except AutoIssue.DoesNotExist:
            sys.stderr.write(
                f"FAIL verify_tdd_lesson: AutoIssue #{issue_id} does not exist.\n"
                f"WHY: the strict-TDD marker references a lesson row, and "
                f"every reference must resolve to a real DB row so the next "
                f"agent can read the lesson via `manage.py read_scoped_lessons`.\n"
                f"UNBLOCK: re-run `manage.py log_tdd_lesson --file ... --red-test "
                f"... --trap ... --fix-shape ...` to create a real row, then "
                f"update the marker with the returned #id.\n"
            )
            raise SystemExit(2)

        category_key = ai.category.key if ai.category else "(no-category)"
        if category_key != "tdd_lesson":
            sys.stderr.write(
                f"FAIL verify_tdd_lesson: AutoIssue #{issue_id} has "
                f"category={category_key!r} but the strict-TDD rule requires "
                f"'tdd_lesson'.\n"
                f"WHY: cross-referencing a code_review_lesson or paper_trail row "
                f"as a TDD lesson hides the Red-Green-Refactor evidence.\n"
                f"UNBLOCK: file a fresh tdd_lesson row via "
                f"`manage.py log_tdd_lesson` and reference its id.\n"
            )
            raise SystemExit(2)

        if ai.status != AutoIssue.STATUS_RESOLVED:
            sys.stderr.write(
                f"FAIL verify_tdd_lesson: AutoIssue #{issue_id} has "
                f"status={ai.status!r} but strict-TDD lessons must be "
                f"'resolved' so they show up in read_scoped_lessons.\n"
                f"UNBLOCK: re-log the cycle (manage.py log_tdd_lesson auto-"
                f"creates with status=resolved).\n"
            )
            raise SystemExit(2)

        lessons = (ai.lessons_learned or "").strip()
        if "Trap:" not in lessons or "Fix shape:" not in lessons:
            sys.stderr.write(
                f"FAIL verify_tdd_lesson: AutoIssue #{issue_id}.lessons_learned "
                f"is missing the two-part `Trap: ... Fix shape: ...` shape.\n"
                f"WHY: the next agent reads this field to learn what tripped "
                f"the prior agent. Empty or one-part lessons are protocol "
                f"violations of the resolved-AutoIssue rule.\n"
                f"UNBLOCK: re-log via `manage.py log_tdd_lesson --trap \"...\" "
                f"--fix-shape \"...\"`.\n"
            )
            raise SystemExit(2)

        self.stdout.write(f"[TDD LESSON VERIFIED: AutoIssue=#{issue_id}]")
