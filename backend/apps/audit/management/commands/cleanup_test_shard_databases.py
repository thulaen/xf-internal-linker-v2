from __future__ import annotations

from datetime import timedelta

from django.core.management.base import BaseCommand

from apps.audit.services import test_database_shards


class Command(BaseCommand):
    help = "Drop expired sharded test databases created by the cluster test runner."

    def add_arguments(self, parser):
        parser.add_argument("--max-age-hours", type=int, default=12)
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        max_age = timedelta(hours=options["max_age_hours"])
        names = test_database_shards.list_shard_databases()
        expired = test_database_shards.expired_shard_databases(names, max_age=max_age)
        for name in expired:
            if not options["dry_run"]:
                test_database_shards.drop_database(name)
            self.stdout.write(f"[TEST DB SHARD EXPIRED: {name}]")
        self.stdout.write(
            f"[TEST DB SHARD CLEANUP: checked={len(names)} expired={len(expired)}]"
        )
