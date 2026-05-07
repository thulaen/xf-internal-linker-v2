"""Exit-code health gate — fail non-zero if the auth_user table is short.

Plain-English: counts the rows in ``auth_user`` and prints them as
JSON. If the count is below ``--min`` (default 1), the command exits
non-zero so a calling script (the safe-rebuild PowerShell script)
can detect data loss without parsing free text.

Used by ``scripts/safe-rebuild.ps1`` to:
  * record the baseline count BEFORE rebuild (``--min 0``), and
  * verify the count is still at least the baseline AFTER rebuild.
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError


class Command(BaseCommand):
    help = "Print the auth_user row count as JSON; non-zero exit if below --min."

    def add_arguments(self, parser):
        parser.add_argument(
            "--min",
            type=int,
            default=1,
            help="Minimum acceptable auth_user count. Below this, exit non-zero.",
        )

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model

        count = get_user_model().objects.count()
        threshold = int(options["min"])
        self.stdout.write(json.dumps({"auth_user_count": count}))
        if count < threshold:
            raise CommandError(
                f"auth_user count {count} is below the required minimum {threshold}."
            )
