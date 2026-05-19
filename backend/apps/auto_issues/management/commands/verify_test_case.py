"""manage.py verify_test_case — validates referenced test case AutoIssues.

Called by `.githooks/check-test-case-mandate.py` (production-mode verifier)
to confirm that `[TEST CASE MAPPING: ... test_cases=#N]` marker IDs resolve
to real `AutoIssue(category='test_case')` rows with non-empty Given/When/Then
in `lessons_learned`.

Exit 0 on pass + prints `[TEST CASE VERIFIED: AutoIssue=#N file=<src>]`.
CommandError (exit non-zero) on any failure.

Spec: docs/TEST-CASE-FIRST-RULE.md
"""

from __future__ import annotations

import re

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.models import AutoIssue


_GIVEN_RE = re.compile(r"\bgiven\b", re.IGNORECASE)
_WHEN_RE = re.compile(r"\bwhen\b", re.IGNORECASE)
_THEN_RE = re.compile(r"\bthen\b", re.IGNORECASE)


class Command(BaseCommand):
    help = "Verify referenced test_case AutoIssue IDs resolve to real rows."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--id", required=True, type=int, action="append", dest="ids",
                            help="AutoIssue primary key to verify. Repeatable.")
        parser.add_argument("--dry-run", action="store_true",
                            help="Run the verification without printing the marker.")

    def handle(self, *args, **opts) -> None:
        for pk in list(dict.fromkeys(opts["ids"])):
            self._verify_one(pk, dry_run=opts["dry_run"])

    def _verify_one(self, pk: int, *, dry_run: bool) -> None:
        try:
            ai = AutoIssue.objects.select_related("category").get(pk=pk)
        except AutoIssue.DoesNotExist as exc:
            raise CommandError(
                f"FAIL verify_test_case: AutoIssue #{pk} does not exist.\n"
                f"WHY: every ID in a `[TEST CASE MAPPING: ... test_cases=#N]` "
                f"marker must point at a real row.\n"
                f"UNBLOCK: file the test case via `manage.py log_test_case "
                f"--file <p> --title \"...\" --given \"...\" --when \"...\" "
                f"--then \"...\"` and use the printed `#N`."
            ) from exc

        cat_key = getattr(ai.category, "key", None) if ai.category else None
        if cat_key != "test_case":
            raise CommandError(
                f"FAIL verify_test_case: AutoIssue #{pk} has category "
                f"{cat_key!r}, not 'test_case'.\n"
                f"WHY: only rows filed via `log_test_case` are valid test "
                f"case contracts. Cross-category references hide stub or "
                f"wrong-shape rows behind real-looking IDs.\n"
                f"UNBLOCK: file a fresh test case for this surface via "
                f"`manage.py log_test_case ...` and update the marker."
            )

        lessons = (ai.lessons_learned or "").strip()
        missing = []
        if not _GIVEN_RE.search(lessons):
            missing.append("Given")
        if not _WHEN_RE.search(lessons):
            missing.append("When")
        if not _THEN_RE.search(lessons):
            missing.append("Then")
        if missing:
            raise CommandError(
                f"FAIL verify_test_case: AutoIssue #{pk} is in the test_case "
                f"category but lessons_learned is missing required BDD "
                f"section(s): {', '.join(missing)}.\n"
                f"WHY: the rule requires Given/When/Then sections so the "
                f"next agent reads a real contract, not prose.\n"
                f"UNBLOCK: re-file the test case via `manage.py log_test_case "
                f"--given \"...\" --when \"...\" --then \"...\"`."
            )

        if dry_run:
            return
        affected = ", ".join(ai.affected_files[:3]) if ai.affected_files else "(none)"
        self.stdout.write(
            f"[TEST CASE VERIFIED: AutoIssue=#{ai.pk} file={affected} "
            f"status={ai.status}]"
        )
