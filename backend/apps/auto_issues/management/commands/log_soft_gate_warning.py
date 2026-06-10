"""Log a pre-commit soft gate warning as a searchable AutoIssue.

Called by scripts/precommit-docker.sh whenever a soft gate fires locally.
Creates or deduplicates an AutoIssue so coverage gaps don't get silently lost.
"""
# xf: no_dry_run -- fire-and-forget command called inline by pre-commit hooks; a dry run would suppress the searchable AutoIssue that is the sole purpose of this command

from __future__ import annotations

import hashlib

from django.core.management.base import BaseCommand

from apps.auto_issues.models import AutoIssue
from apps.auto_issues.services.dedup import upsert_dedup


class Command(BaseCommand):
    help = "Log a pre-commit soft gate warning as a precommit_warn AutoIssue."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--hook",
            required=True,
            help="Name of the soft gate that fired (e.g. check-per-file-coverage).",
        )
        parser.add_argument(
            "--detail",
            default="",
            help="First FAIL line from the hook output (up to 200 chars).",
        )

    def handle(self, *args, **opts) -> None:
        hook = opts["hook"]
        detail = (opts.get("detail") or "").strip()[:200]

        title = f"Soft gate warning: {hook}"
        abstract = detail or f"Pre-commit soft gate '{hook}' fired — no blocking detail captured."

        fingerprint = hashlib.sha1(  # nosec B324
            f"precommit_warn:{hook}".encode()
        ).hexdigest()[:16]

        row, outcome = upsert_dedup(
            canonical=fingerprint,
            source=AutoIssue.SOURCE_PRE_COMMIT_WARNING,
            external_id=hook,
            fingerprint=fingerprint,
            title=title,
            description=abstract,
            affected_files=[],
            severity=AutoIssue.SEVERITY_LOW,
            priority_score=0.25,
            occurrence_count=1,
        )

        marker = f"[SOFT GATE WARNING LOGGED: AutoIssue=#{row.pk} hook={hook} outcome={outcome}]"
        self.stdout.write(marker)
