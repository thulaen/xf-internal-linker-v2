"""Rotate the append-only quality scope decision log on explicit request."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone


class Command(BaseCommand):
    help = "Rotate audit/scope_decisions.jsonl when explicitly requested."

    def add_arguments(self, parser) -> None:
        parser.add_argument("--repo-root", default="/repo")
        parser.add_argument("--keep-empty", action="store_true")

    def handle(self, *args, **options) -> None:
        repo_root = Path(options["repo_root"]).resolve()
        log_path = repo_root / "audit" / "scope_decisions.jsonl"
        if not log_path.exists():
            if options["keep_empty"]:
                log_path.parent.mkdir(parents=True, exist_ok=True)
                log_path.touch()
            self.stdout.write("[SCOPE LOG ROTATED: skipped missing log]")
            return
        if not log_path.is_file():
            raise CommandError("audit/scope_decisions.jsonl is not a file")
        if log_path.stat().st_size == 0:
            self.stdout.write("[SCOPE LOG ROTATED: skipped empty log]")
            return
        stamp = timezone.now().strftime("%Y%m%d-%H%M%S")
        rotated = log_path.with_name(f"scope_decisions-{stamp}.jsonl")
        log_path.replace(rotated)
        log_path.touch()
        self.stdout.write(f"[SCOPE LOG ROTATED: archived={rotated.name}]")
