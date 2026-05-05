"""Check migrations for unsafe data-loss and duplicate-artifact patterns."""

from __future__ import annotations

from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from apps.core.services.data_preservation import (
    PROTECTED_DATA_RULES,
    scan_repo_migrations,
)


class Command(BaseCommand):
    help = "Fail when migrations can wipe protected current-state data."

    def add_arguments(self, parser):
        parser.add_argument(
            "--repo-root",
            default="/repo",
            help="Repository root. Defaults to /repo inside Docker.",
        )
        parser.add_argument(
            "--list-manifest",
            action="store_true",
            help="Print protected tables before scanning.",
        )

    def handle(self, *args, **options):
        repo_root = Path(options["repo_root"]).resolve()
        if options["list_manifest"]:
            for rule in PROTECTED_DATA_RULES:
                self.stdout.write(f"{rule.table}: {rule.policy} - {rule.reason}")

        findings = scan_repo_migrations(repo_root)
        if not findings:
            self.stdout.write(self.style.SUCCESS("Migration data-safety check passed."))
            return

        for finding in findings:
            self.stderr.write(
                f"{finding.path}:{finding.line}: {finding.kind}: {finding.detail}"
            )
        raise CommandError(
            "Unsafe migration pattern found. Preserve current data, mark stale, "
            "or add a documented bounded-retention exception."
        )
