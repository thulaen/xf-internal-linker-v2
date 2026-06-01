"""Ingest captured compiler/linter warnings into deduped SOURCE_COMPILER AutoIssues.

Reads a warning log file (the quality runners tee compiler stderr to one) for a
given language and files one deduped AutoIssue per warning. Supports --dry-run.
Spec: docs/specs/fr-compiler-warning-autoissues.md.
"""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services.compiler_ingest import ingest_compiler_warnings
from apps.auto_issues.services.compiler_warnings import SUPPORTED_LANGUAGES


class Command(BaseCommand):
    help = "File AutoIssues for captured compiler/linter warnings."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--path", required=True, help="Path to the captured warning log.")
        parser.add_argument(
            "--language", required=True, choices=SUPPORTED_LANGUAGES,
            help="Which compiler/linter produced the log.",
        )
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and report counts without writing AutoIssues.",
        )

    def handle(self, *args, **opts) -> None:
        path = Path(opts["path"])
        if not path.is_file():
            raise CommandError(f"--path {path} does not exist or is not a file.")
        text = path.read_text(encoding="utf-8", errors="replace")
        result = ingest_compiler_warnings(text, opts["language"], dry_run=opts["dry_run"])
        prefix = "[COMPILER WARNINGS (dry-run)" if opts["dry_run"] else "[COMPILER WARNINGS"
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}: language={opts['language']} parsed={result['parsed']} "
                f"filed={result['filed']}]"
            )
        )
