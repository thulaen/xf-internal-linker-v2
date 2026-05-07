"""Synchronous on-demand DB snapshot — no Celery dependency.

Plain-English: takes one Postgres snapshot right now, by calling
``apps.core.backups.run_backup_pass`` directly. Designed to be invoked
from the safe-rebuild script BEFORE shutting containers down, so we
never lose the live state if the rebuild goes sideways.

Why not just dispatch the existing Celery task ``backups.run_backups``?
Because the rebuild script runs while Redis may be mid-restart; importing
the celery task module would bring in the broker config and crash. This
command imports only the pure-Python snapshot helper.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Take one Postgres snapshot now (synchronous, no Celery)."

    def handle(self, *args, **options):
        from apps.core.backups import run_backup_pass

        result = run_backup_pass()
        self.stdout.write(json.dumps(result))
        if not result.get("created"):
            raise CommandError(
                "Snapshot was skipped — see the backend logs for the reason "
                "(usually low disk space). The rebuild script will refuse to "
                "continue without a fresh snapshot."
            )
