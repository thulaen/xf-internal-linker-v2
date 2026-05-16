"""manage.py verify_paper_trail_quota — gate for the pre-commit hook."""

from __future__ import annotations

from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.paper_trail.models import PaperTrailEntry

_REQUIRED_QUOTA = 10


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
    help = "Verify the 10 paper-trail picks are resolved with two-part lessons."

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

        duplicate_work = _duplicate_work_errors(ids, rows)
        if duplicate_work:
            raise CommandError("\n".join(duplicate_work))

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


def _duplicate_work_errors(
    ids: list[int],
    rows: dict[int, PaperTrailEntry],
) -> list[str]:
    by_key: dict[str, list[int]] = {}
    for entry_id in ids:
        entry = rows.get(entry_id)
        if entry is None or not entry.canonical_fingerprint:
            continue
        by_key.setdefault(entry.canonical_fingerprint, []).append(entry_id)
    return [
        "Duplicate Paper Trail work is not allowed in one quota: "
        + ", ".join(f"#{entry_id}" for entry_id in entry_ids)
        for entry_ids in by_key.values()
        if len(entry_ids) > 1
    ]
