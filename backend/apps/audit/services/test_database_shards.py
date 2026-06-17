"""Direct Postgres helpers for sharded test databases."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from django.conf import settings


DEFAULT_TEMPLATE_DB = "xf_test_template"
DEFAULT_PREFIX = "xf_t"
DEFAULT_ADMIN_DB = "postgres"
DEFAULT_LOCK_KEY = 260014
_DB_NAME_RE = re.compile(r"^[a-z][a-z0-9_]{0,62}$")
_SHARD_RE = re.compile(r"^xf_t_(?P<stamp>\d{14})_[a-z0-9_]+_s\d+$")


@dataclass(frozen=True)
class AdminConnectionInfo:
    host: str
    port: str
    user: str
    password: str
    dbname: str = DEFAULT_ADMIN_DB


def build_shard_database_name(
    run_id: str,
    shard_index: int,
    *,
    now: datetime | None = None,
    prefix: str = DEFAULT_PREFIX,
) -> str:
    if shard_index < 0:
        raise ValueError("shard_index must be zero or greater")
    stamp = (now or datetime.now(UTC)).strftime("%Y%m%d%H%M%S")
    slug = _slug(run_id)[:24]
    return validate_database_name(f"{prefix}_{stamp}_{slug}_s{shard_index}")


def validate_database_name(name: str) -> str:
    if not _DB_NAME_RE.fullmatch(name):
        raise ValueError(f"unsafe Postgres database name: {name!r}")
    return name


def admin_connection_info(database: str = DEFAULT_ADMIN_DB) -> AdminConnectionInfo:
    db = settings.DATABASES["default"]
    host = os.environ.get("XF_TEST_DB_ADMIN_HOST", str(db.get("HOST", "")))
    if host.lower() == "pgbouncer":
        raise ValueError("test database clone work must connect to Postgres, not PgBouncer")
    return AdminConnectionInfo(
        host=host,
        port=str(os.environ.get("XF_TEST_DB_ADMIN_PORT", db.get("PORT", "5432"))),
        user=str(os.environ.get("XF_TEST_DB_ADMIN_USER", db.get("USER", "postgres"))),
        password=str(os.environ.get("XF_TEST_DB_ADMIN_PASSWORD", db.get("PASSWORD", ""))),
        dbname=database,
    )


def create_database_from_template(
    database_name: str,
    *,
    template_name: str = DEFAULT_TEMPLATE_DB,
    lock_key: int = DEFAULT_LOCK_KEY,
) -> None:
    database_name = validate_database_name(database_name)
    template_name = validate_database_name(template_name)
    with _connect(admin_connection_info()) as conn:
        _execute_locked(conn, lock_key, _create_database_sql(database_name, template_name))


def drop_database(database_name: str) -> None:
    database_name = validate_database_name(database_name)
    with _connect(admin_connection_info()) as conn:
        _run_sql(conn, "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname = %s", database_name)
        _run_sql(conn, _drop_database_sql(database_name))


def list_shard_databases() -> list[str]:
    with _connect(admin_connection_info()) as conn:
        rows = _fetch_all(conn, "SELECT datname FROM pg_database WHERE datname LIKE 'xf\\_t\\_%'")
    return [str(row[0]) for row in rows]


def expired_shard_databases(names: list[str], *, max_age: timedelta) -> list[str]:
    now = datetime.now(UTC)
    expired = []
    for name in names:
        created_at = _created_at_from_name(name)
        if created_at and now - created_at > max_age:
            expired.append(name)
    return expired


def _slug(raw: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", "_", raw.lower()).strip("_")
    return cleaned or "run"


def _connect(info: AdminConnectionInfo) -> Any:
    import psycopg

    return psycopg.connect(
        host=info.host,
        port=info.port,
        user=info.user,
        password=info.password,
        dbname=info.dbname,
        autocommit=True,
    )


def _execute_locked(conn: Any, lock_key: int, sql_text: Any) -> None:
    with conn.cursor() as cursor:
        cursor.execute("SELECT pg_advisory_lock(%s)", (lock_key,))
        try:
            cursor.execute(sql_text)
        finally:
            cursor.execute("SELECT pg_advisory_unlock(%s)", (lock_key,))


def _run_sql(conn: Any, sql_text: Any, *params: object) -> None:
    with conn.cursor() as cursor:
        cursor.execute(sql_text, params or None)


def _fetch_all(conn: Any, sql_text: str) -> list[tuple[Any, ...]]:
    with conn.cursor() as cursor:
        cursor.execute(sql_text)
        return list(cursor.fetchall())


def _create_database_sql(database_name: str, template_name: str) -> Any:
    from psycopg import sql

    return sql.SQL("CREATE DATABASE {} TEMPLATE {}").format(
        sql.Identifier(database_name),
        sql.Identifier(template_name),
    )


def _drop_database_sql(database_name: str) -> Any:
    from psycopg import sql

    return sql.SQL("DROP DATABASE IF EXISTS {}").format(sql.Identifier(database_name))


def _created_at_from_name(name: str) -> datetime | None:
    match = _SHARD_RE.fullmatch(name)
    if not match:
        return None
    return datetime.strptime(match.group("stamp"), "%Y%m%d%H%M%S").replace(tzinfo=UTC)
