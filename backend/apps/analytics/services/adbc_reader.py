"""Arrow-native Postgres reads via ADBC (Arrow Database Connectivity).

Why this module exists:
  The analytics snapshot jobs (telemetry rollup, GSC click window) move
  tens of thousands of rows out of Postgres into Polars/Parquet. The
  Django ORM fetches those as a list of Python tuples, then we zip them
  back into columns — two full passes building throwaway Python objects.
  ADBC streams the same result straight out of Postgres as a columnar
  Arrow table, which Polars wraps with zero copy. No per-row Python
  object churn on the hot export path.

Connection target:
  The libpq URI is built from ``django.db.connection.settings_dict`` —
  NOT ``settings.DATABASES`` — because Django rewrites the connection's
  ``NAME`` to the test database (e.g. ``test_xf_linker``) at test time.
  Reading the live connection's settings means ADBC talks to the same
  database the ORM is using, in tests and in production alike.

Test visibility:
  ADBC opens its OWN libpq connection, so it only sees COMMITTED rows.
  Tests that seed data and then call a function backed by this reader
  must use ``TransactionTestCase`` (which commits) rather than the
  default transactional ``TestCase`` (whose writes are never committed
  and so are invisible to a second connection).

Reference: Apache Arrow ADBC — https://arrow.apache.org/adbc/
"""

from __future__ import annotations

from typing import Any
from urllib.parse import quote


def postgres_uri() -> str:
    """Build a libpq URI for the ORM's *current* default connection."""
    from django.db import connection

    cfg = connection.settings_dict
    user = quote(str(cfg.get("USER") or ""), safe="")
    password = quote(str(cfg.get("PASSWORD") or ""), safe="")
    host = cfg.get("HOST") or "localhost"
    port = cfg.get("PORT") or "5432"
    name = cfg.get("NAME") or ""
    if user and password:
        auth = f"{user}:{password}@"
    elif user:
        auth = f"{user}@"
    else:
        auth = ""
    return f"postgresql://{auth}{host}:{port}/{name}"


def read_sql_polars(sql: str, params: list[Any] | None = None):
    """Run ``sql`` over the default Postgres connection, return a Polars DataFrame.

    Placeholders use libpq's native numbered style — ``$1``, ``$2``, … — and
    ``params`` binds them positionally, so callers never string-format
    untrusted values into the query. (The ADBC PostgreSQL driver forwards SQL
    straight to libpq; the manager's nominal ``pyformat`` paramstyle does not
    apply.)
    """
    import adbc_driver_postgresql.dbapi as pg
    import polars as pl

    with pg.connect(postgres_uri()) as conn:
        with conn.cursor() as cur:
            cur.execute(sql, parameters=params or None)
            table = cur.fetch_arrow_table()
    return pl.from_arrow(table)


__all__ = ["postgres_uri", "read_sql_polars"]
