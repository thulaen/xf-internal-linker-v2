"""Ingest one smart-build compilation failure as a deduped AutoIssue."""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services.build_failures import failure_from_payload, ingest_build_failure


class Command(BaseCommand):
    help = "Create or update one AutoIssue for a failed smart-build compilation."

    def add_arguments(self, parser):
        parser.add_argument("--payload-json", required=True)

    def handle(self, *args, **options):
        try:
            payload = json.loads(options["payload_json"])
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid build failure JSON: {exc}") from exc
        issue, outcome = ingest_build_failure(failure_from_payload(payload))
        self.stdout.write(
            f"[BUILD FAILURE AUTOISSUE: {outcome} AutoIssue=#{issue.pk}]"
        )
