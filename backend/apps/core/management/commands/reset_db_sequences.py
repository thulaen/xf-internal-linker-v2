"""Reset Postgres id sequences to MAX(id) for every model (idempotent).

Repairs stale sequences after a database restore so the next INSERT cannot
collide with an existing row. AutoIssue #20182: after a restore the
django_celery_results_taskresult sequence lagged MAX(id) by ~6000, producing
~818 duplicate-key errors/hour until the sequence was advanced to MAX(id).

Reuses Django's built-in ``connection.ops.sequence_reset_sql`` so the emitted
``setval(..., coalesce(max(id), 1), max(id) IS NOT NULL)`` statements are the
canonical, idempotent repair — running this twice is a no-op.
"""
from __future__ import annotations

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand, CommandError
from django.core.management.color import no_style
from django.db import DEFAULT_DB_ALIAS, connections


class Command(BaseCommand):
    help = (
        "Reset every model's id sequence to MAX(id) (idempotent). Run after a "
        "database restore to prevent duplicate-key inserts (AutoIssue #20182)."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            action="append",
            dest="app",
            default=None,
            help="Limit to these app labels (default: every installed app).",
        )
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Database alias to repair.",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the setval SQL without executing it.",
        )

    def handle(self, *args, **options):
        connection = connections[options["database"]]
        models = self._models_for(options["app"])
        sql = connection.ops.sequence_reset_sql(no_style(), models)
        if not sql:
            self.stdout.write("[RESET DB SEQUENCES: no sequences to reset]")
            return
        if options["dry_run"]:
            for statement in sql:
                self.stdout.write(statement)
            self.stdout.write(
                f"[RESET DB SEQUENCES DRY RUN: {len(sql)} statement(s) not executed]"
            )
            return
        with connection.cursor() as cursor:
            for statement in sql:
                cursor.execute(statement)
        self.stdout.write(
            f"[RESET DB SEQUENCES: reset {len(sql)} sequence(s) to MAX(id)]"
        )

    @staticmethod
    def _models_for(app_labels):
        if not app_labels:
            return list(django_apps.get_models())
        models = []
        for label in app_labels:
            try:
                config = django_apps.get_app_config(label)
            except LookupError as exc:
                raise CommandError(f"Unknown app label: {label}") from exc
            models.extend(config.get_models())
        return models
