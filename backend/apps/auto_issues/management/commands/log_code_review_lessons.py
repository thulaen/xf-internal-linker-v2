"""manage.py log_code_review_lessons — Rule G command.

Logs an agent's self-review of a code change as an AutoIssue with
category='code_review_lesson'. Dedup via canonical_fingerprint so
repeated reviews of the same area collapse into one row.

Emits one of two markers:
  [CODE REVIEW LESSON LOGGED: AutoIssue=#N title="..." abstract_words=W]
  [CODE REVIEW LESSON DEDUPED: matched AutoIssue=#N]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.concept_tags import collect_and_validate_tags, merge_tags
from apps.auto_issues.models import AutoIssue, AutoIssueCategory
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


_MAX_TITLE_CHARS = 200
_MAX_ABSTRACT_WORDS = 600
_CATEGORY_KEY = "code_review_lesson"
_CATEGORY_LABEL = "Code review lesson"


def _get_or_create_category() -> AutoIssueCategory:
    cat, _ = AutoIssueCategory.objects.get_or_create(
        key=_CATEGORY_KEY,
        defaults={
            "label": _CATEGORY_LABEL,
            "description": (
                "Self-review lesson logged by an agent after a code change, "
                "per Rule G. Includes 'no issues found' reviews; deduped via "
                "canonical_fingerprint."
            ),
            "sort_order": 200,
        },
    )
    return cat


_SEVERITY_MAP = {
    "none": AutoIssue.SEVERITY_LOW,
    "low": AutoIssue.SEVERITY_LOW,
    "medium": AutoIssue.SEVERITY_MEDIUM,
    "high": AutoIssue.SEVERITY_HIGH,
    "critical": AutoIssue.SEVERITY_CRITICAL,
}


def _build_observation(*, canonical: str, first_seen, now, count: int, abstract: str, agent: str) -> dict:
    return {
        "source": "code_review",
        "external_id": f"code_review::{canonical}",
        "first_seen": first_seen.isoformat() if first_seen else now.isoformat(),
        "last_seen": now.isoformat(),
        "occurrence_count": count,
        "abstract_excerpt": abstract[:200],
        "agent": agent,
    }


def _lessons_for_review(*, abstract: str, agent: str, now) -> str:
    is_clean = abstract.lower().startswith("no issues")
    lessons = abstract if is_clean else (
        f"Trap: {abstract[:300]}\n"
        f"Fix shape: agent self-review at {timezone.now().isoformat()}; "
        f"see affected_files for the touched paths."
    )
    if "Trap:" in lessons and "Fix shape:" in lessons:
        return lessons
    return (
        f"Trap: agents may not realise this area was reviewed and "
        f"found clean by {agent} on {now.date().isoformat()}.\n"
        f"Fix shape: {abstract}"
    )


def _merge_existing_review(*, existing: AutoIssue, files: list[str], abstract: str,
                           canonical: str, agent: str, concept_tags: list[str],
                           now) -> int:
    existing.occurrence_count += 1
    existing.last_seen = now
    existing.source_observations = [
        *(existing.source_observations or []),
        _build_observation(
            canonical=canonical,
            first_seen=existing.first_seen,
            now=now,
            count=existing.occurrence_count,
            abstract=abstract,
            agent=agent,
        ),
    ]
    existing.affected_files = list(
        dict.fromkeys((existing.affected_files or []) + files)
    )
    existing.concept_tags = merge_tags(existing.concept_tags, concept_tags)
    existing.save()
    return int(existing.pk)


def _create_review(*, title: str, abstract: str, files: list[str],
                   canonical: str, category: AutoIssueCategory, agent: str,
                   severity: str, concept_tags: list[str], now) -> int:
    ext_id = f"code_review::{canonical}"
    ai = AutoIssue.objects.create(
        source=AutoIssue.SOURCE_AGENT,
        external_id=ext_id,
        fingerprint=ext_id[:64],
        canonical_fingerprint=canonical,
        title=title[:512],
        description=abstract[:4000],
        affected_files=files,
        severity=severity,
        category=category,
        status=AutoIssue.STATUS_RESOLVED,
        resolved_at=now,
        resolved_by=agent,
        lessons_learned=_lessons_for_review(abstract=abstract, agent=agent, now=now),
        concept_tags=concept_tags,
        occurrence_count=1,
        last_seen=now,
        source_observations=[
            _build_observation(
                canonical=canonical,
                first_seen=now,
                now=now,
                count=1,
                abstract=abstract,
                agent=agent,
            )
        ],
    )
    return int(ai.pk)


class Command(BaseCommand):
    help = "Log a code-review lesson as an AutoIssue (Rule G)."

    def add_arguments(self, parser):
        parser.add_argument("--file", dest="files", action="append",
                            required=True,
                            help="Repo-relative source file path (repeatable).")
        parser.add_argument("--title", required=True,
                            help=f"Descriptive title, max {_MAX_TITLE_CHARS} chars.")
        parser.add_argument("--abstract", required=True,
                            help=f"Summary, max {_MAX_ABSTRACT_WORDS} words.")
        parser.add_argument("--severity", default="low",
                            choices=sorted(_SEVERITY_MAP.keys()))
        parser.add_argument("--autoissue-id", type=int, default=None,
                            help="Optional: link to an AutoIssue being resolved.")
        parser.add_argument("--concept-tag", action="append", default=[],
                            help="Approved concept tag; repeat for more than one.")
        parser.add_argument("--agent", default="claude")
        parser.add_argument(
            "--bulk-per-file",
            action="store_true",
            help=(
                "When several --file values are supplied, print one logged "
                "or deduped marker per file without restarting Django."
            ),
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Show what would change without applying.",
        )

    def handle(self, *args, **opts):
        title = (opts["title"] or "").strip()
        abstract = (opts["abstract"] or "").strip()
        files = [f.strip() for f in opts["files"] if f.strip()]

        if not title:
            raise CommandError(
                "FAIL log_code_review_lessons: --title is empty.\n"
                "WHY: Rule G requires every code-review lesson to have a "
                "non-empty descriptive title so future agents can search "
                "for prior reviews of the same area.\n"
                "UNBLOCK: Re-run with --title \"<descriptive phrase>\"."
            )
        if len(title) > _MAX_TITLE_CHARS:
            raise CommandError(
                f"FAIL log_code_review_lessons: title is {len(title)} chars "
                f"(max {_MAX_TITLE_CHARS}).\n"
                "WHY: Rule G caps titles at 200 characters so the "
                "AutoIssue list stays scannable.\n"
                "UNBLOCK: Shorten the title; move detail into the abstract."
            )
        word_count = len(abstract.split())
        if word_count > _MAX_ABSTRACT_WORDS:
            raise CommandError(
                f"FAIL log_code_review_lessons: abstract is {word_count} "
                f"words (max {_MAX_ABSTRACT_WORDS}).\n"
                "WHY: Rule G caps abstracts at 600 words so reviews stay "
                "focused and the AutoIssue table doesn't become a wiki.\n"
                "UNBLOCK: Trim the abstract or file a paper-trail entry "
                "for the long-form details."
            )

        if opts["bulk_per_file"]:
            for file_path in files:
                self._write_review_marker(
                    title=title,
                    abstract=abstract,
                    files=[file_path],
                    opts=opts,
                )
            return

        self._write_review_marker(
            title=title,
            abstract=abstract,
            files=files,
            opts=opts,
        )

    def _write_review_marker(self, *, title: str, abstract: str, files: list[str], opts):
        word_count = len(abstract.split())
        canonical = canonical_fingerprint(title)
        if opts["dry_run"]:
            self.stdout.write(
                f"[CODE REVIEW LESSON DRY-RUN: title=\"{title[:60]}\" "
                f"files={len(files)} abstract_words={word_count}]"
            )
            return
        category = _get_or_create_category()
        # Cheap SQL exact-match dedup: same canonical_fingerprint and
        # category collapse into the same row.
        existing = AutoIssue.objects.filter(
            canonical_fingerprint=canonical,
            category=category,
        ).first()
        agent = opts["agent"][:64]
        severity = _SEVERITY_MAP[opts["severity"]]
        concept_tags = collect_and_validate_tags(opts)
        now = timezone.now()

        if existing is not None:
            issue_id = _merge_existing_review(
                existing=existing,
                files=files,
                abstract=abstract,
                canonical=canonical,
                agent=agent,
                concept_tags=concept_tags,
                now=now,
            )
            self.stdout.write(
                f"[CODE REVIEW LESSON DEDUPED: matched AutoIssue=#{issue_id}]"
            )
            return

        issue_id = _create_review(
            title=title,
            abstract=abstract,
            files=files,
            canonical=canonical,
            category=category,
            agent=agent,
            severity=severity,
            concept_tags=concept_tags,
            now=now,
        )
        self.stdout.write(
            f"[CODE REVIEW LESSON LOGGED: AutoIssue=#{issue_id} "
            f"title=\"{title[:60]}\" abstract_words={word_count}]"
        )
