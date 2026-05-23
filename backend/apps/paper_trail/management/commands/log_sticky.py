"""File or update a sticky Paper Trail entry.

Sticky entries hold standing-orders documents whose body may run up to
10,000 words (versus the 1,200-word cap on every other status). The
abstract is read verbatim from a file on disk so very long bodies
(including newlines, Unicode, and the policy text the user supplies)
land in the database without command-line escaping headaches.

Two modes:

* Create: omit --id. The command files a new sticky.
* Update: pass --id <existing-sticky-id>. The command replaces the
  body and updates the title / severity / deferred_by fields. Used by
  any commit that carries the [STICKY N EDIT: ...] marker.

Examples:

    docker compose exec -T backend python manage.py log_sticky \\
        --title "Spec-Driven Gradual Rewrite Policy" \\
        --abstract-file /repo/backend/tmp/sticky_1_body.md \\
        --severity critical \\
        --deferred-by user

    docker compose exec -T backend python manage.py log_sticky \\
        --id 11 \\
        --abstract-file /repo/backend/tmp/sticky_1_body_v2.md
"""
from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry


_VALID_SEVERITIES = {
    PaperTrailEntry.SEVERITY_CRITICAL,
    PaperTrailEntry.SEVERITY_HIGH,
    PaperTrailEntry.SEVERITY_MEDIUM,
    PaperTrailEntry.SEVERITY_LOW,
}


def _sha256_prefix(text: str, length: int = 16) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    return digest[:length]


# xf: no_dry_run -- log_sticky is a one-shot administrative command run by
# the user or by an agent that has just produced a new policy body file;
# preview semantics add no value because the file already exists on disk
# and can be inspected directly before invoking the command. Rolling back
# a sticky create or update is done via the next log_sticky --id <id>
# invocation with the previous body file.
class Command(BaseCommand):
    """Create or update a sticky Paper Trail entry from an on-disk body."""

    help = "File or update a sticky paper-trail entry from an abstract file."

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            type=int,
            default=None,
            help="Existing sticky id to update; omit to create a new sticky.",
        )
        parser.add_argument(
            "--title",
            type=str,
            default=None,
            help="Title (required when creating; optional when updating).",
        )
        parser.add_argument(
            "--abstract-file",
            type=str,
            required=True,
            help="Path to a file whose contents become the sticky abstract.",
        )
        parser.add_argument(
            "--severity",
            type=str,
            default=PaperTrailEntry.SEVERITY_CRITICAL,
            help="Severity (critical|high|medium|low). Default: critical.",
        )
        parser.add_argument(
            "--deferred-by",
            type=str,
            default="user",
            help="Who filed or updated this sticky. Default: user.",
        )
        parser.add_argument(
            "--category",
            type=str,
            default=PaperTrailEntry.CATEGORY_DOCUMENTATION,
            help="Category. Default: documentation.",
        )

    def handle(self, *args, **options) -> None:
        sticky_id: Optional[int] = options["id"]
        title: Optional[str] = options["title"]
        abstract_path = Path(options["abstract_file"])
        severity: str = options["severity"]
        deferred_by: str = options["deferred_by"]
        category: str = options["category"]

        if severity not in _VALID_SEVERITIES:
            raise CommandError(
                f"--severity must be one of {sorted(_VALID_SEVERITIES)}, "
                f"got {severity!r}."
            )

        if not abstract_path.is_file():
            raise CommandError(
                f"--abstract-file {abstract_path} does not exist or is "
                "not a file. Save the sticky body to that path first."
            )

        body = abstract_path.read_text(encoding="utf-8")
        if not body.strip():
            raise CommandError(
                f"--abstract-file {abstract_path} is empty. The sticky "
                "body must be the full policy text."
            )

        word_count = len(body.split())
        if word_count > PaperTrailEntry._STICKY_ABSTRACT_WORD_CAP:
            raise CommandError(
                f"sticky body is {word_count} words, exceeds the "
                f"{PaperTrailEntry._STICKY_ABSTRACT_WORD_CAP}-word cap. "
                "Move long-form detail into linked specs under docs/specs/ "
                "or ADRs under docs/adr/ and reference them from the "
                "sticky body."
            )

        sha_prefix = _sha256_prefix(body)
        now = timezone.now()

        if sticky_id is None:
            # Create.
            if not title:
                raise CommandError("--title is required when creating a new sticky.")
            entry = PaperTrailEntry(
                title=title,
                abstract=body,
                category=category,
                severity=severity,
                status=PaperTrailEntry.STATUS_STICKY,
                deferred_at=now,
                deferred_by=deferred_by,
            )
            # Skip the auto-fingerprint logic that runs in save() for
            # active statuses; sticky entries bypass dedup.
            entry.full_clean(exclude=["fingerprint", "canonical_fingerprint"])
            entry.save()
            self.stdout.write(
                f"[STICKY FILED: id={entry.id} title={entry.title!r} "
                f"sha256={sha_prefix} word_count={word_count}]"
            )
            return

        # Update.
        try:
            entry = PaperTrailEntry.objects.get(id=sticky_id)
        except PaperTrailEntry.DoesNotExist as exc:
            raise CommandError(f"sticky #{sticky_id} not found.") from exc

        if entry.status != PaperTrailEntry.STATUS_STICKY:
            raise CommandError(
                f"paper-trail entry #{sticky_id} has status={entry.status!r}, "
                "not 'sticky'. log_sticky only updates sticky entries."
            )

        previous_sha = _sha256_prefix(entry.abstract or "")
        entry.abstract = body
        if title:
            entry.title = title
        entry.severity = severity
        entry.deferred_by = deferred_by
        entry.full_clean(exclude=["fingerprint", "canonical_fingerprint"])
        entry.save()
        self.stdout.write(
            f"[STICKY UPDATED: id={entry.id} title={entry.title!r} "
            f"previous_sha256={previous_sha} new_sha256={sha_prefix} "
            f"word_count={word_count}]"
        )
