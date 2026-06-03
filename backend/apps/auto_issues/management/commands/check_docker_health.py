from __future__ import annotations

import json
from pathlib import Path

from django.core.management.base import BaseCommand

from apps.auto_issues.services.docker_health import (
    DEFAULT_TIMEOUT_SECONDS,
    check_docker_health,
    file_docker_health_results,
)


class Command(BaseCommand):
    help = "Probe Windows and Mint Docker daemons and file AutoIssues for failures."

    def add_arguments(self, parser):
        parser.add_argument(
            "--timeout-seconds",
            type=int,
            default=DEFAULT_TIMEOUT_SECONDS,
            help="Per-probe timeout.",
        )
        parser.add_argument(
            "--no-file",
            action="store_true",
            help="Probe only; do not create or update AutoIssues.",
        )
        parser.add_argument(
            "--from-json",
            default="",
            help="Read precomputed host-side Docker probe results from this JSON file.",
        )

    def handle(self, *args, **options):
        if options["from_json"]:
            payload = json.loads(Path(options["from_json"]).read_text(encoding="utf-8-sig"))
            result = file_docker_health_results(
                payload["results"],
                file_issues=not options["no_file"],
            )
        else:
            result = check_docker_health(
                timeout_seconds=options["timeout_seconds"],
                file_issues=not options["no_file"],
            )
        self.stdout.write(
            "[DOCKER HEALTH READ: "
            f"checked={result['checked']} failures={result['failures']} "
            f"status={result['status']}]"
        )
        self.stdout.write(json.dumps(result, sort_keys=True))
