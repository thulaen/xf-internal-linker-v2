"""Restore a Postgres snapshot taken by Group L #91 (apps.core.backups).

Plain-English: this is the destructive flip-side of the daily backup
task. It runs ``pg_restore --clean`` against the live database,
which means it WIPES the existing schema before restoring. There is
no automatic rollback — once you confirm and run this, the prior
state is gone unless a more recent snapshot exists.

Usage:
    # List available snapshots and pick one
    docker compose exec backend python manage.py restore_db_snapshot --list

    # Restore by exact filename (must be in backups/)
    docker compose exec backend python manage.py restore_db_snapshot \\
        snapshot-20260428-023000.dump --confirm

    # Or restore the most recent snapshot
    docker compose exec backend python manage.py restore_db_snapshot \\
        --latest --confirm

The ``--confirm`` flag is mandatory. Without it the command prints
the plan and exits without touching the database.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.backups import (
    DEFAULT_BACKUP_DIR,
    list_existing_snapshots,
    restore_from_snapshot,
)


class Command(BaseCommand):
    help = "Restore a Postgres snapshot from backups/ (DESTRUCTIVE — wipes the live DB)."

    def add_arguments(self, parser):
        parser.add_argument(
            "filename",
            nargs="?",
            default=None,
            help=(
                "Filename of the snapshot to restore (just the basename, "
                "the file must already live in backups/). Mutually "
                "exclusive with --latest and --list."
            ),
        )
        parser.add_argument(
            "--latest",
            action="store_true",
            help="Restore the most recent snapshot.",
        )
        parser.add_argument(
            "--list",
            action="store_true",
            help="List available snapshots and exit (no restore).",
        )
        parser.add_argument(
            "--confirm",
            action="store_true",
            help=(
                "Required to actually run the restore. Without it, the "
                "command prints the plan and exits."
            ),
        )

    def handle(self, *args, **options):
        snapshots = list_existing_snapshots(DEFAULT_BACKUP_DIR)

        if options.get("list"):
            self._print_list(snapshots)
            return

        # Pick the snapshot to restore.
        snapshot_path: Path | None = None
        if options.get("latest"):
            if not snapshots:
                raise CommandError(
                    f"No snapshots found in {DEFAULT_BACKUP_DIR}. Run the "
                    "daily backup task first or copy a .dump file there."
                )
            snapshot_path = snapshots[-1]  # newest by sort
        elif options.get("filename"):
            candidate = DEFAULT_BACKUP_DIR / options["filename"]
            if not candidate.is_file():
                raise CommandError(
                    f"Snapshot file not found: {candidate}. Run with --list "
                    "to see available snapshots."
                )
            snapshot_path = candidate
        else:
            raise CommandError(
                "Pass either a filename, --latest, or --list. See "
                "'python manage.py restore_db_snapshot --help'."
            )

        # Always print the plan before the destructive call.
        size_mb = snapshot_path.stat().st_size // (1024 * 1024)
        self.stdout.write("")
        self.stdout.write(self.style.WARNING("=== RESTORE PLAN ==="))
        self.stdout.write(f"Snapshot:    {snapshot_path}")
        self.stdout.write(f"Size:        {size_mb} MB")
        self.stdout.write(
            "Effect:      pg_restore --clean --if-exists (DROPS existing "
            "schema before restoring)"
        )
        self.stdout.write("")

        if not options.get("confirm"):
            self.stdout.write(
                self.style.NOTICE(
                    "Dry run only. Re-run with --confirm to actually restore."
                )
            )
            return

        self.stdout.write(self.style.WARNING("Running restore..."))
        ok = restore_from_snapshot(
            snapshot_path=snapshot_path,
            confirm_destructive=True,
        )
        if ok:
            self.stdout.write(self.style.SUCCESS("Restore complete."))
        else:
            raise CommandError(
                "Restore failed. Check the backend logs for the pg_restore "
                "stderr — the most common causes are wrong DB credentials, "
                "the postgres container being down, or insufficient disk."
            )

    def _print_list(self, snapshots):
        if not snapshots:
            self.stdout.write(
                f"No snapshots found in {DEFAULT_BACKUP_DIR}. Run the "
                "daily backup task first."
            )
            return
        self.stdout.write(f"Snapshots in {DEFAULT_BACKUP_DIR}:")
        for path in snapshots:
            size_mb = path.stat().st_size // (1024 * 1024)
            self.stdout.write(f"  {path.name}  ({size_mb} MB)")
