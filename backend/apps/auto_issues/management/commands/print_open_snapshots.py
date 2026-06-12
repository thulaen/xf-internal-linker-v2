"""Print the [SNAPSHOTS READ: ...] session-start marker.

The Go "snapshotd" daemon that stored per-AutoIssue evidence snapshots
was retired on 2026-06-11 (ADR 0007 — Python + Rust only). Nothing ever
created snapshots in production, so the store was always empty; this
command now always emits the skipped form, which the snapshotd-ritual
hook accepts:

    [SNAPSHOTS READ: skipped — snapshotd unavailable]

The command stays (rather than being deleted) because the session-start
payload service invokes it by name on every gate call. If a Python
snapshot store is ever built, this command is where the full picked
form returns.

Usage::

    docker compose exec -T backend python manage.py print_open_snapshots
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

_SKIPPED_MARKER = "[SNAPSHOTS READ: skipped — snapshotd unavailable]"


class Command(BaseCommand):
    help = (
        "Print the [SNAPSHOTS READ: ...] marker required at session start. "
        "Always the skipped form since the snapshot daemon was retired."
    )

    def add_arguments(self, parser):
        # Kept for call-site compatibility; the flags have no effect now
        # that the snapshot store is gone.
        parser.add_argument("--by-severity", action="store_true", default=True)
        parser.add_argument("--top", type=int, default=3)

    def handle(self, *args, **options):
        self.stdout.write(_SKIPPED_MARKER)
