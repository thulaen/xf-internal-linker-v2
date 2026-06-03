"""File one hook finding as a real AutoIssue."""

from __future__ import annotations

import hashlib

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue, AutoIssueCategory

_MAX_TITLE_CHARS = 200
_MAX_DESCRIPTION_CHARS = 4000
_VALID_SEVERITIES = {
    AutoIssue.SEVERITY_LOW,
    AutoIssue.SEVERITY_MEDIUM,
    AutoIssue.SEVERITY_HIGH,
    AutoIssue.SEVERITY_CRITICAL,
}


def file_hook_finding(
    *,
    category: str,
    severity: str,
    subject: str,
    message: str,
    agent: str = "codex",
    external_id: str = "",
    lessons_learned: str = "",
) -> tuple[AutoIssue, bool]:
    """Create or update one AutoIssue for a hook finding."""
    _validate_inputs(category, severity, subject, message)
    category_row = _get_or_create_category(category)
    now = timezone.now()
    fingerprint = _fingerprint(category, subject, message)
    issue_external_id = external_id.strip() or f"hook_finding::{category}::{fingerprint}"
    existing = AutoIssue.objects.filter(external_id=issue_external_id).first()
    if existing is not None:
        _update_existing(existing, subject, message, agent, now, lessons_learned)
        return existing, False
    return _create_issue(
        category_row,
        severity,
        subject,
        message,
        agent,
        now,
        fingerprint,
        issue_external_id,
        lessons_learned,
    ), True


def _validate_inputs(category: str, severity: str, subject: str, message: str) -> None:
    if not category.strip():
        raise CommandError("category must not be empty")
    if severity not in _VALID_SEVERITIES:
        raise CommandError("severity must be low, medium, high, or critical")
    if not subject.strip() or ":" not in subject:
        raise CommandError("subject must contain a wrapper or file reference")
    if len(message.strip()) < 20:
        raise CommandError("message must be at least 20 characters")


def _get_or_create_category(key: str) -> AutoIssueCategory:
    label = key.replace("_", " ").title()
    category, _ = AutoIssueCategory.objects.get_or_create(
        key=key,
        defaults={
            "label": label,
            "description": "Hook finding filed automatically by repository quality checks.",
            "sort_order": 260,
        },
    )
    return category


def _fingerprint(category: str, subject: str, message: str) -> str:
    raw = f"{category}{subject}{message[:200]}"
    return hashlib.sha1(raw.encode("utf-8"), usedforsecurity=False).hexdigest()[:16]


def _title(message: str) -> str:
    first_sentence = message.split(". ", 1)[0]
    return first_sentence[:_MAX_TITLE_CHARS]


def _observation(subject: str, message: str, agent: str, now, occurrence_count: int) -> dict:
    return {
        "source": "hook_finding",
        "subject": subject,
        "message": message,
        "first_seen": now.isoformat(),
        "last_seen": now.isoformat(),
        "occurrence_count": occurrence_count,
        "agent": agent[:64],
    }


def _update_existing(
    issue: AutoIssue,
    subject: str,
    message: str,
    agent: str,
    now,
    lessons_learned: str,
) -> None:
    issue.occurrence_count += 1
    issue.last_seen = now
    issue.status = AutoIssue.STATUS_OPEN
    issue.resolved_at = None
    issue.resolved_by = ""
    issue.fix_commit_sha = ""
    issue.source_observations = [
        *(issue.source_observations or []),
        _observation(subject, message, agent, now, issue.occurrence_count),
    ][:50]
    update_fields = [
        "occurrence_count",
        "last_seen",
        "status",
        "resolved_at",
        "resolved_by",
        "fix_commit_sha",
        "source_observations",
    ]
    if lessons_learned.strip():
        issue.lessons_learned = lessons_learned.strip()
        update_fields.append("lessons_learned")
    issue.save(update_fields=update_fields)


def _create_issue(
    category: AutoIssueCategory,
    severity: str,
    subject: str,
    message: str,
    agent: str,
    now,
    fingerprint: str,
    external_id: str,
    lessons_learned: str,
) -> AutoIssue:
    return AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        category=category,
        severity=severity,
        title=_title(message),
        description=message[:_MAX_DESCRIPTION_CHARS],
        external_id=external_id,
        canonical_fingerprint=fingerprint,
        fingerprint=fingerprint,
        status=AutoIssue.STATUS_OPEN,
        occurrence_count=1,
        first_seen=now,
        last_seen=now,
        lessons_learned=lessons_learned.strip() or _default_lessons(message),
        source_observations=[_observation(subject, message, agent, now, 1)],
        concept_tags=_concept_tags(category.key, subject),
    )


def _default_lessons(message: str) -> str:
    return f"Trap: {message}\nFix shape: <UNBLOCK section>"


def _concept_tags(category: str, subject: str) -> list[str]:
    path = subject.split(":", 1)[0].replace("\\", "/")
    parts = [part for part in path.split("/")[:-1] if part and part != "apps"]
    return sorted({category.split("_", 1)[0], *parts})


class Command(BaseCommand):
    help = "File one hook finding as an AutoIssue."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--category", required=True)
        parser.add_argument("--severity", required=True)
        parser.add_argument("--subject", required=True)
        parser.add_argument("--message", required=True)
        parser.add_argument("--agent", default="codex")
        parser.add_argument("--external-id", default="")
        parser.add_argument("--lessons-learned", default="")

    def handle(self, *args, **options) -> None:
        issue, created = file_hook_finding(
            category=options["category"],
            severity=options["severity"],
            subject=options["subject"],
            message=options["message"],
            agent=options["agent"],
            external_id=options["external_id"],
            lessons_learned=options["lessons_learned"],
        )
        if created:
            self.stdout.write(f"[HOOK FINDING FILED: AutoIssue=#{issue.pk}]")
        else:
            self.stdout.write(f"[HOOK FINDING DEDUPED: matched AutoIssue=#{issue.pk}]")
