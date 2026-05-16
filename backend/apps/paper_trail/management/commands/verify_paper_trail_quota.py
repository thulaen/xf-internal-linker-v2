"""manage.py verify_paper_trail_quota — gate for the pre-commit hook."""

from __future__ import annotations

from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.paper_trail.models import PaperTrailEntry

# Lowered from 10 to 3 on 2026-05-16. The quota also now fires on every
# commit (not just code-changing commits) — see check-paper-trail-read.py.
_REQUIRED_QUOTA = 3


def _parse_resolved_after(raw: str | None) -> datetime | None:
    if not raw:
        return None
    raw = raw.strip()
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d"):
        try:
            return datetime.strptime(raw, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    raise CommandError(
        f"Could not parse --resolved-after timestamp {raw!r}. "
        "Use 'YYYY-MM-DD HH:MM' or ISO 8601."
    )


class Command(BaseCommand):
    help = "Verify the 3 paper-trail picks are resolved with two-part lessons."

    def add_arguments(self, parser):
        parser.add_argument("--ids", nargs="+", type=int, required=True)
        parser.add_argument("--resolved-after", default=None)

    def handle(self, *args, **opts):
        ids = list(opts["ids"])
        if len(ids) != _REQUIRED_QUOTA:
            raise CommandError(
                f"Expected exactly {_REQUIRED_QUOTA} ids, got {len(ids)}."
            )
        if len(set(ids)) != _REQUIRED_QUOTA:
            raise CommandError("--ids contains duplicates.")

        rows = {e.pk: e for e in PaperTrailEntry.objects.filter(pk__in=ids)}
        missing = [i for i in ids if i not in rows]
        if missing:
            raise CommandError(
                f"PaperTrailEntry not found: {', '.join(f'#{i}' for i in missing)}"
            )

        unresolved = [
            i for i in ids if rows[i].status != PaperTrailEntry.STATUS_RESOLVED
        ]
        if unresolved:
            raise CommandError(
                f"Not resolved: {', '.join(f'#{i}' for i in unresolved)}"
            )

        no_timestamp = [i for i in ids if rows[i].resolved_at is None]
        if no_timestamp:
            raise CommandError(
                f"Missing resolved_at: {', '.join(f'#{i}' for i in no_timestamp)}"
            )

        cutoff = _parse_resolved_after(opts.get("resolved_after"))
        if cutoff is not None:
            stale = [
                i for i in ids
                if rows[i].resolved_at is not None
                and rows[i].resolved_at <= cutoff
            ]
            if stale:
                raise CommandError(
                    "These were resolved BEFORE the cutoff "
                    f"({cutoff.isoformat()}): "
                    f"{', '.join(f'#{i}' for i in stale)}"
                )

        empty_lessons = [
            i for i in ids
            if not rows[i].resolution_lessons.strip()
            or "Trap:" not in rows[i].resolution_lessons
            or "Fix shape:" not in rows[i].resolution_lessons
        ]
        if empty_lessons:
            raise CommandError(
                "Missing or malformed resolution_lessons (need Trap: + Fix shape:): "
                f"{', '.join(f'#{i}' for i in empty_lessons)}"
            )

        self.stdout.write(f"[PAPER TRAIL QUOTA VERIFIED: {_REQUIRED_QUOTA} resolved]")
