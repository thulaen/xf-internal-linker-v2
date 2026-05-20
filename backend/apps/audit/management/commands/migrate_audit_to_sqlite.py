from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.audit.services.audit_lookup import (
    DEFAULT_JSONL_PATH,
    DEFAULT_SQLITE_PATH,
    migrate_jsonl_to_sqlite,
)


class Command(BaseCommand):
    help = "Build the SQLite resolved-issue lookup index from the JSONL audit index."

    def add_arguments(self, parser):
        parser.add_argument("--jsonl", default=str(DEFAULT_JSONL_PATH))
        parser.add_argument("--sqlite", default=str(DEFAULT_SQLITE_PATH))
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        jsonl_path = Path(options["jsonl"])
        sqlite_path = Path(options["sqlite"])
        if options["dry_run"]:
            self.stdout.write(
                f"[AUDIT SQLITE MIGRATION DRY-RUN: jsonl={jsonl_path} sqlite={sqlite_path}]"
            )
            return
        row_count = migrate_jsonl_to_sqlite(
            jsonl_path=jsonl_path,
            sqlite_path=sqlite_path,
        )
        self.stdout.write(
            f"[AUDIT SQLITE MIGRATED: rows={row_count} sqlite={sqlite_path}]"
        )
