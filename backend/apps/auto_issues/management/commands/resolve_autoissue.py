"""Resolve existing AutoIssue rows with lessons learned."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


class Command(BaseCommand):
    help = "Resolve one or more AutoIssue rows after a verified fix."

    def add_arguments(self, parser):
        parser.add_argument("--id", dest="ids", action="append", type=int, required=True)
        parser.add_argument("--lessons-learned", required=True)
        parser.add_argument("--agent", default="codex")

    def handle(self, *args, **options):
        ids = _dedupe_ids(options["ids"])
        lessons = options["lessons_learned"].strip()
        _validate_lessons(lessons)
        issues = _load_issues(ids)
        now = timezone.now()

        for issue_id in ids:
            _mark_resolved(issues[issue_id], options["agent"], lessons, now)

        joined = ", ".join(f"#{issue_id}" for issue_id in ids)
        self.stdout.write(f"[AUTOISSUES RESOLVED: {len(ids)} — {joined}]")


def _dedupe_ids(ids: list[int]) -> list[int]:
    return list(dict.fromkeys(ids))


def _validate_lessons(lessons: str) -> None:
    if "Trap:" not in lessons or "Fix shape:" not in lessons:
        raise CommandError(
            "--lessons-learned must include both 'Trap:' and 'Fix shape:'."
        )


def _load_issues(ids: list[int]) -> dict[int, AutoIssue]:
    issues = {issue.id: issue for issue in AutoIssue.objects.filter(id__in=ids)}
    missing = [issue_id for issue_id in ids if issue_id not in issues]
    if missing:
        joined = ", ".join(f"#{issue_id}" for issue_id in missing)
        raise CommandError(f"AutoIssue id(s) not found: {joined}")
    return issues


def _mark_resolved(issue: AutoIssue, agent: str, lessons: str, now) -> None:
    issue.status = AutoIssue.STATUS_RESOLVED
    issue.resolved_at = now
    issue.resolved_by = agent[:64]
    issue.lessons_learned = lessons
    issue.save(update_fields=["status", "resolved_at", "resolved_by", "lessons_learned"])
