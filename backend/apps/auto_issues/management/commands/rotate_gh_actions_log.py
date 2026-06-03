"""Rotate GitHub Actions failure history on explicit request."""

from __future__ import annotations

from datetime import datetime, timezone as dt_timezone
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.auto_issues.services import gh_actions_history


class Command(BaseCommand):
    help = "Rotate audit/github_actions_failures.jsonl when explicitly requested."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--before", required=True)
        parser.add_argument("--repo-root", default="/repo")

    def handle(self, *args, **options) -> None:
        cutoff = _parse_cutoff(options["before"])
        repo_root = Path(options["repo_root"]).resolve()
        history_path = repo_root / "audit" / "github_actions_failures.jsonl"
        moved, kept = gh_actions_history.rotate_before(cutoff, history_path)
        self.stdout.write(f"[GH ACTIONS LOG ROTATED: moved={moved} kept={kept}]")


def _parse_cutoff(raw: str) -> datetime:
    try:
        parsed = datetime.strptime(raw, "%Y-%m-%d")
    except ValueError as exc:
        raise CommandError("--before must use YYYY-MM-DD.") from exc
    return parsed.replace(tzinfo=dt_timezone.utc)
