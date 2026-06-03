"""Import CodeQL SARIF reports into AutoIssues."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services import codeql


class Command(BaseCommand):
    help = "Import CodeQL SARIF reports and dedupe them into AutoIssues."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--path", action="append", required=True)
        parser.add_argument("--language", required=True)
        parser.add_argument("--max-open", type=int, default=10)

    def handle(self, *args, **options) -> None:
        paths = [_sarif_path(item) for item in options["path"]]
        result = codeql.ingest_sarif_paths(
            paths,
            language=options["language"],
            max_open=options["max_open"],
        )
        try:
            codeql.verify_codeql_autoissues(max_open=options["max_open"], block_open=False)
        except ValueError as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(
            f"[CODEQL SARIF INGESTED: language={options['language']} "
            f"created={result.created} updated={result.updated} "
            f"skipped={result.skipped} total={result.total}]"
        )


def _sarif_path(value: str) -> Path:
    path = Path(value)
    if path.is_dir():
        raise CommandError("--path must point at a SARIF file, not a directory")
    return path
