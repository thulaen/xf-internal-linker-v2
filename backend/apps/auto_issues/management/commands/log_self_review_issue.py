"""Log a scoped self-review finding as an AutoIssue."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.concept_tags import collect_and_validate_tags, merge_tags
from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.categories import normalize_category_key
from apps.auto_issues.services.dedup import upsert_dedup
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_SEVERITY_SCORE = {
    AutoIssue.SEVERITY_LOW: 0.25,
    AutoIssue.SEVERITY_MEDIUM: 0.5,
    AutoIssue.SEVERITY_HIGH: 0.8,
    AutoIssue.SEVERITY_CRITICAL: 1.0,
}
_CATEGORIES = (
    "security",
    "performance",
    "maintainability",
    "readability",
    "correctness",
    "error-handling",
    "concurrency",
    "contract",
    "architecture",
    "resources",
    "tech-debt",
    "observability",
    "internationalization",
)


class Command(BaseCommand):
    help = "Record a bad practice found during the task-scoped self-review."

    def add_arguments(self, parser):
        parser.add_argument("--title", required=True)
        parser.add_argument("--description", required=True)
        parser.add_argument("--file", action="append", dest="files", required=True)
        parser.add_argument(
            "--category",
            default="correctness",
            help=f"Category key. Built-in examples: {', '.join(_CATEGORIES)}.",
        )
        parser.add_argument(
            "--severity",
            choices=[choice for choice, _ in AutoIssue.SEVERITY_CHOICES],
            default=AutoIssue.SEVERITY_MEDIUM,
        )
        parser.add_argument("--fixed", action="store_true")
        parser.add_argument("--lessons-learned", default="")
        parser.add_argument("--concept-tag", action="append", default=[],
                            help="Approved concept tag; repeat for more than one.")
        parser.add_argument("--agent", default="codex")
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without applying.",
        )

    def handle(self, *args, **options):
        lessons = options["lessons_learned"].strip()
        if options["fixed"] and not lessons:
            raise CommandError("--lessons-learned is required when --fixed is used.")

        concept_tags = collect_and_validate_tags(options)
        category_key = _parse_category(options["category"])
        canonical = canonical_fingerprint(options["title"], f"self-review:{category_key}")
        if options["dry_run"]:
            files = [path for path in options["files"] if path]
            self.stdout.write(
                f"[SELF REVIEW ISSUE DRY-RUN: title=\"{options['title'][:60]}\" "
                f"category={category_key} files={len(files)}]"
            )
            return
        issue, outcome = upsert_dedup(
            canonical=canonical,
            source=AutoIssue.SOURCE_AGENT,
            external_id=f"self-review:{canonical}",
            fingerprint=canonical,
            title=options["title"],
            description=_format_description(category_key, options["description"]),
            affected_files=options["files"],
            category_key=category_key,
            severity=options["severity"],
            priority_score=_SEVERITY_SCORE[options["severity"]],
            occurrence_count=1,
        )
        issue.concept_tags = merge_tags(issue.concept_tags, concept_tags)
        issue.save(update_fields=["concept_tags"])
        if options["fixed"]:
            _mark_resolved(issue, options["agent"], lessons)
            outcome = f"{outcome}, resolved"
        self.stdout.write(f"AutoIssue #{issue.id} {outcome}: {issue.title}")


def _mark_resolved(issue: AutoIssue, agent: str, lessons: str) -> None:
    issue.status = AutoIssue.STATUS_RESOLVED
    issue.resolved_at = timezone.now()
    issue.resolved_by = agent[:64]
    issue.lessons_learned = lessons
    issue.save(update_fields=["status", "resolved_at", "resolved_by", "lessons_learned"])


def _format_description(category: str, description: str) -> str:
    return f"Self-review category: {category}\n\n{description}"


def _parse_category(raw_category: str) -> str:
    try:
        return normalize_category_key(raw_category)
    except ValueError as exc:
        raise CommandError(str(exc)) from exc
