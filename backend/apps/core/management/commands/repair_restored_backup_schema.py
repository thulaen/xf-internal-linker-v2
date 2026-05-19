"""Repair migration history after restoring an older database backup."""

from __future__ import annotations

from dataclasses import dataclass

from django.core.management.base import BaseCommand, CommandError
from django.db import DEFAULT_DB_ALIAS, connections, transaction
from django.db.migrations.recorder import MigrationRecorder

FROZEN_DATACLASS = dataclass(frozen=True)


@FROZEN_DATACLASS
class RestoreAppSpec:
    app: str
    migrations: tuple[str, ...]
    required_tables: frozenset[str]
    required_columns: dict[str, frozenset[str]]
    required_indexes: frozenset[str] = frozenset()
    required_constraints: frozenset[str] = frozenset()


@FROZEN_DATACLASS
class SchemaSnapshot:
    tables: set[str]
    columns: dict[str, set[str]]
    indexes: set[str]
    constraints: set[str]


@FROZEN_DATACLASS
class RepairDecision:
    spec: RestoreAppSpec
    missing_migrations: tuple[str, ...]
    missing_schema: tuple[str, ...]

    @property
    def can_record(self) -> bool:
        return bool(self.missing_migrations) and not self.missing_schema


SCHEMA_SPECS = (
    RestoreAppSpec(
        app="auto_issues",
        migrations=(
            "0011_autoissue_categories",
            "0012_autoissue_spam_score",
            "0013_autoissue_concept_tags",
        ),
        required_tables=frozenset(
            {"auto_issues_autoissue", "auto_issues_autoissuecategory"}
        ),
        required_columns={
            "auto_issues_autoissue": frozenset(
                {"category_id", "spam_score", "concept_tags"}
            ),
            "auto_issues_autoissuecategory": frozenset(
                {
                    "created_at",
                    "description",
                    "id",
                    "is_active",
                    "key",
                    "label",
                    "parent_id",
                    "sort_order",
                    "updated_at",
                }
            ),
        },
        required_indexes=frozenset({"auto_issues_categor_3172b8_idx"}),
    ),
    RestoreAppSpec(
        app="paper_trail",
        migrations=(
            "0001_initial",
            "0002_alter_papertrailentry_abstract",
            "0003_remove_papertrailentry_uniq_papertrail_active_category_fingerprint_and_more",
            "0004_papertrailentry_test_case_autoissue_id",
        ),
        required_tables=frozenset({"paper_trail_papertrailentry"}),
        required_columns={
            "paper_trail_papertrailentry": frozenset(
                {
                    "acceptance_criteria",
                    "abstract",
                    "category",
                    "canonical_fingerprint",
                    "deferred_at",
                    "evidence_level",
                    "fingerprint",
                    "id",
                    "integrity_check_result",
                    "last_seen",
                    "status",
                    "superseded_by_id",
                    "test_case_autoissue_id",
                    "title",
                }
            )
        },
        required_indexes=frozenset(
            {
                "paper_trail_papertrailentry_test_case_autoissue_id_1c0412a5",
                "paper_trail_status_f1a0df_idx",
                "uniq_papertrail_active_category_fingerprint",
            }
        ),
    ),
)


class Command(BaseCommand):
    help = "Repair migration history after restoring an older verified database backup."

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Print the migration-history rows that would be repaired.",
        )
        parser.add_argument(
            "--check",
            action="store_true",
            help="Exit non-zero if the live schema and migration history disagree.",
        )
        parser.add_argument(
            "--database",
            default=DEFAULT_DB_ALIAS,
            help="Database alias to inspect and repair.",
        )

    def handle(self, *args, **options):
        if options["dry_run"] and options["check"]:
            raise CommandError("Use either --dry-run or --check, not both.")

        connection = connections[options["database"]]
        snapshot = collect_schema_snapshot(connection)
        applied = collect_applied_migrations(connection, SCHEMA_SPECS)
        decisions = build_repair_decisions(snapshot, applied)

        if options["check"]:
            self._check(decisions)
            return

        _raise_on_unsafe_history(decisions)
        if options["dry_run"]:
            _print_dry_run(self.stdout, decisions)
            return

        _record_repairable_history(connection, self.stdout, decisions)

    def _check(self, decisions: list[RepairDecision]) -> None:
        disagreements = _format_disagreements(decisions)
        if disagreements:
            raise CommandError(
                "missing migration history or schema mismatch: "
                + "; ".join(disagreements)
            )
        self.stdout.write("[RESTORED BACKUP SCHEMA OK: checked auto_issues,paper_trail]")


def collect_schema_snapshot(connection) -> SchemaSnapshot:
    return SchemaSnapshot(
        tables=_fetch_table_names(connection),
        columns=_fetch_columns_by_table(connection),
        indexes=_fetch_names(
            connection,
            "select indexname from pg_indexes where schemaname = current_schema()",
        ),
        constraints=_fetch_names(
            connection,
            "select conname from pg_constraint "
            "where connamespace = current_schema()::regnamespace",
        ),
    )


def collect_applied_migrations(
    connection,
    specs: tuple[RestoreAppSpec, ...],
) -> dict[str, set[str]]:
    recorder = MigrationRecorder(connection)
    apps = [spec.app for spec in specs]
    applied = {app: set() for app in apps}
    if not recorder.has_table():
        return applied
    rows = (
        recorder.Migration.objects.using(connection.alias)
        .filter(app__in=apps)
        .values_list("app", "name")
    )
    for app, name in rows:
        applied[app].add(name)
    return applied


def build_repair_decisions(
    snapshot: SchemaSnapshot,
    applied_by_app: dict[str, set[str]],
) -> list[RepairDecision]:
    specs = [spec for spec in SCHEMA_SPECS if spec.app in applied_by_app]
    return [
        RepairDecision(
            spec=spec,
            missing_migrations=tuple(
                migration
                for migration in spec.migrations
                if migration not in applied_by_app[spec.app]
            ),
            missing_schema=tuple(_missing_schema_items(snapshot, spec)),
        )
        for spec in specs
    ]


def _missing_schema_items(snapshot: SchemaSnapshot, spec: RestoreAppSpec) -> list[str]:
    missing = [table for table in spec.required_tables if table not in snapshot.tables]
    for table, required_columns in spec.required_columns.items():
        present_columns = snapshot.columns.get(table, set())
        missing.extend(
            f"{table}.{column}"
            for column in required_columns
            if column not in present_columns
        )
    missing.extend(index for index in spec.required_indexes if index not in snapshot.indexes)
    missing.extend(
        constraint
        for constraint in spec.required_constraints
        if constraint not in snapshot.constraints
    )
    return sorted(missing)


def _fetch_table_names(connection) -> set[str]:
    query = (
        "select table_name from information_schema.tables "
        "where table_schema = current_schema() and table_type = 'BASE TABLE'"
    )
    return _fetch_names(connection, query)


def _fetch_columns_by_table(connection) -> dict[str, set[str]]:
    query = (
        "select table_name, column_name from information_schema.columns "
        "where table_schema = current_schema()"
    )
    columns: dict[str, set[str]] = {}
    with connection.cursor() as cursor:
        cursor.execute(query)
        for table, column in cursor.fetchall():
            columns.setdefault(table, set()).add(column)
    return columns


def _fetch_names(connection, query: str) -> set[str]:
    with connection.cursor() as cursor:
        cursor.execute(query)
        return {row[0] for row in cursor.fetchall()}


def _raise_on_unsafe_history(decisions: list[RepairDecision]) -> None:
    unsafe = [
        decision
        for decision in decisions
        if decision.missing_migrations and decision.missing_schema
    ]
    if unsafe:
        raise CommandError(
            "Refusing to repair migration history because live schema is missing: "
            + "; ".join(_format_missing_schema(unsafe))
        )


def _print_dry_run(stdout, decisions: list[RepairDecision]) -> None:
    repairable = [decision for decision in decisions if decision.can_record]
    if not repairable:
        stdout.write("[RESTORED BACKUP SCHEMA DRY RUN: no repairable history found]")
        return
    for app, migration in _iter_missing_migration_names(repairable):
        stdout.write(f"[RESTORED BACKUP SCHEMA DRY RUN: would record {app}.{migration}]")


def _record_repairable_history(connection, stdout, decisions: list[RepairDecision]) -> None:
    repairable = [decision for decision in decisions if decision.can_record]
    if not repairable:
        stdout.write("[RESTORED BACKUP SCHEMA OK: no stale migration history found]")
        return
    recorder = MigrationRecorder(connection)
    with transaction.atomic(using=connection.alias):
        recorder.ensure_schema()
        for app, migration in _iter_missing_migration_names(repairable):
            recorder.record_applied(app, migration)
            stdout.write(f"[RESTORED BACKUP SCHEMA RECORDED: {app}.{migration}]")


def _iter_missing_migration_names(decisions: list[RepairDecision]):
    for decision in decisions:
        for migration in decision.missing_migrations:
            yield decision.spec.app, migration


def _format_disagreements(decisions: list[RepairDecision]) -> list[str]:
    disagreements: list[str] = []
    for decision in decisions:
        if decision.missing_migrations:
            migrations = ",".join(decision.missing_migrations)
            disagreements.append(f"{decision.spec.app} missing migration history {migrations}")
        if decision.missing_schema:
            schema = ",".join(decision.missing_schema)
            disagreements.append(f"{decision.spec.app} missing live schema {schema}")
    return disagreements


def _format_missing_schema(decisions: list[RepairDecision]) -> list[str]:
    return [
        f"{decision.spec.app}={','.join(decision.missing_schema)}"
        for decision in decisions
    ]
