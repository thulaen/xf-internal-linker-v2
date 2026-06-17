from __future__ import annotations

from django.conf import settings
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import connections

from apps.audit.services import test_database_shards


class Command(BaseCommand):
    help = "Rebuild the direct-Postgres template database used by test shards."

    def add_arguments(self, parser):
        parser.add_argument("--template-name", default=test_database_shards.DEFAULT_TEMPLATE_DB)
        parser.add_argument("--source-template", default="template0")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        template_name = test_database_shards.validate_database_name(options["template_name"])
        source_template = test_database_shards.validate_database_name(options["source_template"])
        if options["dry_run"]:
            self.stdout.write(f"[TEST DB TEMPLATE DRY-RUN: rebuild {template_name}]")
            return
        test_database_shards.drop_database(template_name)
        test_database_shards.create_database_from_template(
            template_name,
            template_name=source_template,
        )
        _run_migrations_against_template(template_name)
        self.stdout.write(f"[TEST DB TEMPLATE READY: {template_name}]")


def _run_migrations_against_template(template_name: str) -> None:
    alias = "xf_test_template_rebuild"
    settings.DATABASES[alias] = {
        **settings.DATABASES["default"],
        "NAME": template_name,
        "TEST": {},
    }
    try:
        call_command("migrate", database=alias, interactive=False, verbosity=0)
    finally:
        connections[alias].close()
        settings.DATABASES.pop(alias, None)
