"""Backfill `canonical_fingerprint` + `source_observations` for existing rows.

Run this once after deploying migration 0003. New rows created by the
pickers always populate these fields, but rows that pre-date the migration
have empty defaults and won't be merged correctly until they're backfilled.

Idempotent: rows that already have a non-empty `canonical_fingerprint`
are skipped. Re-running adds no work.
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.fingerprinting import canonical_fingerprint


class Command(BaseCommand):
    help = "Backfill canonical_fingerprint + source_observations on rows that pre-date migration 0003."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print what would be backfilled, don't modify rows.",
        )

    def handle(self, *args, **opts):
        rows_to_fix = AutoIssue.objects.filter(canonical_fingerprint="")
        total = rows_to_fix.count()
        if not total:
            self.stdout.write("Nothing to backfill — all rows have canonical_fingerprint populated.")
            return

        self.stdout.write(f"Backfilling {total} row(s)...")
        for row in rows_to_fix:
            culprit = (row.affected_files or [""])[0] if row.affected_files else ""
            canonical = canonical_fingerprint(row.title or "", culprit)
            obs = {
                "source": row.source,
                "external_id": row.external_id,
                "first_seen": row.first_seen.isoformat() if row.first_seen else "",
                "last_seen": row.last_seen.isoformat() if row.last_seen else "",
                "occurrence_count": row.occurrence_count,
            }
            self.stdout.write(
                f"  #{row.id} [{row.source}] → canonical={canonical}"
            )
            if not opts["dry_run"]:
                row.canonical_fingerprint = canonical
                if not row.source_observations:
                    row.source_observations = [obs]
                row.save(update_fields=["canonical_fingerprint", "source_observations"])
        if opts["dry_run"]:
            self.stdout.write("DRY RUN — no rows modified.")
        else:
            self.stdout.write(f"Backfilled {total} row(s).")
