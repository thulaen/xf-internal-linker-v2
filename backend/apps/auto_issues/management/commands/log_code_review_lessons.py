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
        parser.add_argument("--agent", default="claude")

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

        canonical = canonical_fingerprint(title)
        category = _get_or_create_category()
        # Cheap SQL exact-match dedup: same canonical_fingerprint and
        # category collapse into the same row.
        existing = AutoIssue.objects.filter(
            canonical_fingerprint=canonical,
            category=category,
        ).first()
        agent = opts["agent"][:64]
        severity = _SEVERITY_MAP[opts["severity"]]
        now = timezone.now()

        if existing is not None:
            existing.occurrence_count += 1
            existing.last_seen = now
            # Append a source-observation so the audit trail is complete.
            obs = {
                "source": "code_review",
                "external_id": f"code_review::{canonical}",
                "first_seen": existing.first_seen.isoformat()
                if existing.first_seen else now.isoformat(),
                "last_seen": now.isoformat(),
                "occurrence_count": existing.occurrence_count,
                "abstract_excerpt": abstract[:200],
                "agent": agent,
            }
            existing.source_observations = [
                *(existing.source_observations or []),
                obs,
            ]
            # Merge affected_files (unique).
            merged = list(dict.fromkeys((existing.affected_files or []) + files))
            existing.affected_files = merged
            existing.save()
            self.stdout.write(
                f"[CODE REVIEW LESSON DEDUPED: matched AutoIssue=#{existing.pk}]"
            )
            return

        ext_id = f"code_review::{canonical}"
        is_clean = abstract.lower().startswith("no issues")
        lessons = abstract if is_clean else (
            f"Trap: {abstract[:300]}\n"
            f"Fix shape: agent self-review at {timezone.now().isoformat()}; "
            f"see affected_files for the touched paths."
        )
        # Ensure both halves are present per the resolved-AutoIssue rule.
        if "Trap:" not in lessons or "Fix shape:" not in lessons:
            # Augment a clean review with the required two-part shape.
            lessons = (
                f"Trap: agents may not realise this area was reviewed and "
                f"found clean by {agent} on {now.date().isoformat()}.\n"
                f"Fix shape: {abstract}"
            )

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
            lessons_learned=lessons,
            occurrence_count=1,
            last_seen=now,
            source_observations=[
                {
                    "source": "code_review",
                    "external_id": ext_id,
                    "first_seen": now.isoformat(),
                    "last_seen": now.isoformat(),
                    "occurrence_count": 1,
                    "abstract_excerpt": abstract[:200],
                    "agent": agent,
                }
            ],
        )
        self.stdout.write(
            f"[CODE REVIEW LESSON LOGGED: AutoIssue=#{ai.pk} "
            f"title=\"{title[:60]}\" abstract_words={word_count}]"
        )
