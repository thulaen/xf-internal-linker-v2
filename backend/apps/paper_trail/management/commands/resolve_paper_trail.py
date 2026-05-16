"""manage.py resolve_paper_trail — close out one or more entries."""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.paper_trail.models import PaperTrailEntry
from apps.paper_trail.services import dedup as dedup_service


def _validate_lessons(text: str) -> None:
    if not text:
        raise CommandError("--lessons-learned is required and must be non-empty.")
    if "Trap:" not in text:
        raise CommandError(
            "lessons must include a 'Trap:' section explaining the non-obvious context."
        )
    if "Fix shape:" not in text:
        raise CommandError(
            "lessons must include a 'Fix shape:' section explaining what worked."
        )


class Command(BaseCommand):
    help = "Resolve one or more PaperTrailEntry rows after a verified fix."

    def add_arguments(self, parser):
        parser.add_argument(
            "--id",
            dest="ids",
            action="append",
            type=int,
            required=True,
        )
        parser.add_argument("--lessons-learned", required=True)
        parser.add_argument("--agent", default="codex")
        parser.add_argument("--commit-sha", default="")

    def handle(self, *args, **opts):
        lessons = opts["lessons_learned"].strip()
        _validate_lessons(lessons)
        ids = list({int(i) for i in opts["ids"]})  # unique

        entries = list(PaperTrailEntry.objects.filter(pk__in=ids))
        found = {e.pk for e in entries}
        missing = [i for i in ids if i not in found]
        if missing:
            raise CommandError(
                f"PaperTrailEntry not found: {', '.join(f'#{i}' for i in missing)}"
            )

        now = timezone.now()
        agent = opts["agent"][:64]
        commit_sha = opts["commit_sha"][:40]

        resolved_ids: list[int] = []
        for entry in entries:
            entry.status = PaperTrailEntry.STATUS_RESOLVED
            entry.resolved_at = now
            entry.resolved_by = agent
            entry.resolution_lessons = lessons
            entry.resolution_commit_sha = commit_sha
            try:
                entry.save()
            except ValidationError as exc:
                raise CommandError(str(exc)) from exc
            dedup_service.remove_entry(entry.pk)
            resolved_ids.append(entry.pk)

        joined = ", ".join(f"#{i}" for i in resolved_ids)
        self.stdout.write(
            f"[PAPER TRAIL RESOLVED: {len(resolved_ids)} — {joined}]"
        )
