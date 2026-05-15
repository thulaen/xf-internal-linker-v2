"""Prune disposable quality-run scratch folders."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand

from apps.auto_issues.services.quality_artifacts import prune_quality_artifacts
from apps.auto_issues.services.quality_evidence import prune_old_raw_snippets


class Command(BaseCommand):
    help = "Delete old mutation, coverage, and test scratch folders from a safe root."

    def add_arguments(self, parser) -> None:
        # The prune service validates this scratch root before deleting anything.
        parser.add_argument("--root", default="/tmp", type=Path)  # nosec B108
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--prune-old-raw-snippets", action="store_true")

    def handle(self, *args, **options) -> None:
        results = prune_quality_artifacts(
            root=options["root"],
            dry_run=not options["apply"],
        )
        for result in results:
            action = "deleted" if result.deleted else "would delete"
            self.stdout.write(f"{action}: {result.path} ({result.bytes_found} bytes)")
        if options["prune_old_raw_snippets"] and options["apply"]:
            pruned = prune_old_raw_snippets()
            self.stdout.write(f"QUALITY RAW SNIPPETS PRUNED: {pruned}")
        self.stdout.write(f"QUALITY ARTIFACTS FOUND: {len(results)}")
