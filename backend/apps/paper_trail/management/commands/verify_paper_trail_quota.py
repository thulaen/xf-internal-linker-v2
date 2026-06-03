"""manage.py verify_paper_trail_quota — gate for the pre-commit hook."""

from __future__ import annotations

from datetime import datetime, timezone

from django.core.management.base import BaseCommand, CommandError

from apps.paper_trail.models import PaperTrailEntry

_REQUIRED_QUOTA = 10
_SESSION_TYPE_CHOICES = ("docs", "infrastructure", "reconciliation", "feature")
_SESSION_TYPE_QUOTAS = {
    "docs": 0,
    "reconciliation": 3,
    "infrastructure": 5,
    "feature": 10,
}


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
        parser.add_argument("--ids", nargs="+", type=int)
        parser.add_argument("--resolved-after", default=None)
        parser.add_argument("--hard", action="store_true")
        parser.add_argument(
            "--session-type",
            choices=_SESSION_TYPE_CHOICES,
            default="feature",
            help="Session type scales the verify quota (docs=0, reconciliation=3, infrastructure=5, feature=10).",
        )

    def handle(self, *args, **opts):
        cutoff = _parse_resolved_after(opts.get("resolved_after"))
        session_type = opts.get("session_type") or "feature"
        required_quota = _SESSION_TYPE_QUOTAS.get(session_type, _REQUIRED_QUOTA)

        if required_quota == 0:
            self.stdout.write(
                self.style.SUCCESS(f"[PAPER TRAIL QUOTA VERIFIED: docs — no quota required]")
            )
            return

        ids = list(opts["ids"] or [])
        if not ids:
            if not opts.get("hard"):
                raise CommandError("--ids is required unless --hard is used.")
            ids = _hard_mode_ids(cutoff, required_quota)
            if len(ids) != required_quota:
                short = required_quota - len(ids)
                raise CommandError(
                    f"paper-trail: {len(ids)} of {required_quota} resolved "
                    f"({short} short)"
                )
        if len(ids) != required_quota:
            raise CommandError(
                f"Expected exactly {required_quota} ids, got {len(ids)}."
            )
        if len(set(ids)) != required_quota:
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

        if cutoff is not None:
            stale = [
                i
                for i in ids
                if rows[i].resolved_at is not None and rows[i].resolved_at <= cutoff
            ]
            if stale:
                raise CommandError(
                    "These were resolved BEFORE the cutoff "
                    f"({cutoff.isoformat()}): "
                    f"{', '.join(f'#{i}' for i in stale)}"
                )

        empty_lessons = [
            i
            for i in ids
            if not rows[i].resolution_lessons.strip()
            or "Trap:" not in rows[i].resolution_lessons
            or "Fix shape:" not in rows[i].resolution_lessons
        ]
        if empty_lessons:
            raise CommandError(
                "Missing or malformed resolution_lessons (need Trap: + Fix shape:): "
                f"{', '.join(f'#{i}' for i in empty_lessons)}"
            )

        self.stdout.write(f"[PAPER TRAIL QUOTA VERIFIED: {required_quota} resolved]")


def _hard_mode_ids(cutoff: datetime | None, limit: int = _REQUIRED_QUOTA) -> list[int]:
    queryset = PaperTrailEntry.objects.filter(
        status=PaperTrailEntry.STATUS_RESOLVED,
        resolved_at__isnull=False,
    )
    if cutoff is not None:
        queryset = queryset.filter(resolved_at__gt=cutoff)
    return list(
        queryset.order_by("-resolved_at", "-id").values_list("id", flat=True)[:limit]
    )


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
