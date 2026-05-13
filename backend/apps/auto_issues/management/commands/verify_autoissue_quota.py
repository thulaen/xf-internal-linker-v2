"""Verify that a handoff's 30 picked AutoIssues were truly resolved."""

from __future__ import annotations

from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


REQUIRED_AUTOISSUE_FIXES = 30


class Command(BaseCommand):
    help = "Verify the 30 AutoIssue records named in the handoff are resolved."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--ids",
            nargs="+",
            required=True,
            help="AutoIssue IDs from the [REGISTRY READ] marker, without drought-log IDs.",
        )
        parser.add_argument(
            "--resolved-after",
            help="Previous handoff timestamp, formatted as YYYY-MM-DD HH:MM.",
        )

    def handle(self, *args, **opts) -> None:
        issue_ids = _parse_issue_ids(opts["ids"])
        resolved_after = _parse_resolved_after(opts.get("resolved_after"))
        errors = _quota_errors(issue_ids, resolved_after)
        if errors:
            raise CommandError("\n".join(errors))
        self.stdout.write(
            self.style.SUCCESS(
                f"[AUTOISSUE QUOTA VERIFIED: {REQUIRED_AUTOISSUE_FIXES} resolved]"
            )
        )


def _parse_issue_ids(raw_ids: list[str]) -> list[int]:
    issue_ids: list[int] = []
    for raw_id in raw_ids:
        try:
            issue_ids.append(int(raw_id.strip().removeprefix("#")))
        except ValueError as exc:
            raise CommandError(f"AutoIssue ID must be a number: {raw_id}") from exc
    return issue_ids


def _parse_resolved_after(raw_stamp: str | None) -> datetime | None:
    if not raw_stamp:
        return None
    try:
        parsed = datetime.strptime(raw_stamp, "%Y-%m-%d %H:%M")
    except ValueError as exc:
        raise CommandError(
            "--resolved-after must use YYYY-MM-DD HH:MM, for example 2026-05-13 05:45"
        ) from exc
    return timezone.make_aware(parsed, timezone.get_current_timezone())


def _quota_errors(issue_ids: list[int], resolved_after: datetime | None) -> list[str]:
    errors = _count_and_duplicate_errors(issue_ids)
    if errors:
        return errors
    issues = {issue.id: issue for issue in AutoIssue.objects.filter(id__in=issue_ids)}
    errors.extend(_missing_issue_errors(issue_ids, issues))
    errors.extend(_issue_state_errors(issue_ids, issues, resolved_after))
    return errors


def _count_and_duplicate_errors(issue_ids: list[int]) -> list[str]:
    errors: list[str] = []
    if len(issue_ids) != REQUIRED_AUTOISSUE_FIXES:
        errors.append(
            f"Expected {REQUIRED_AUTOISSUE_FIXES} picked AutoIssues, found {len(issue_ids)}."
        )
    duplicates = sorted({issue_id for issue_id in issue_ids if issue_ids.count(issue_id) > 1})
    if duplicates:
        errors.append(f"Duplicate picked AutoIssue IDs are not allowed: {_render_ids(duplicates)}.")
    return errors


def _missing_issue_errors(
    issue_ids: list[int], issues: dict[int, AutoIssue]
) -> list[str]:
    missing = [issue_id for issue_id in issue_ids if issue_id not in issues]
    if not missing:
        return []
    return [f"Picked AutoIssue IDs do not exist: {_render_ids(missing)}."]


def _issue_state_errors(
    issue_ids: list[int],
    issues: dict[int, AutoIssue],
    resolved_after: datetime | None,
) -> list[str]:
    errors: list[str] = []
    for issue_id in issue_ids:
        issue = issues.get(issue_id)
        if issue is None:
            continue
        errors.extend(_single_issue_errors(issue, resolved_after))
    return errors


def _single_issue_errors(
    issue: AutoIssue, resolved_after: datetime | None
) -> list[str]:
    errors: list[str] = []
    if issue.status != AutoIssue.STATUS_RESOLVED:
        errors.append(f"#{issue.id} is {issue.status}, not resolved.")
    if issue.resolved_at is None:
        errors.append(f"#{issue.id} has no resolved_at time.")
    elif resolved_after and issue.resolved_at <= resolved_after:
        errors.append(f"#{issue.id} was resolved before the previous handoff.")
    if not issue.lessons_learned.strip():
        errors.append(f"#{issue.id} has no lessons_learned note.")
    return errors


def _render_ids(issue_ids: list[int]) -> str:
    return ", ".join(f"#{issue_id}" for issue_id in issue_ids)
