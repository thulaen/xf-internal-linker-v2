"""Local analytical SQL engine over Parquet snapshots (Apache DataFusion).

Why this module exists:
  Heavy read-only aggregations (multi-window trailing averages, group-bys
  over analytics snapshots) do not belong on the transactional Postgres
  connection. DataFusion is a Rust query engine that executes SQL directly
  against Parquet files, so large scans never hold a database connection
  and never compete with user-facing queries.

Reference: Apache DataFusion documentation — https://datafusion.apache.org/

History note (2026-06-10): the original version of this class registered a
hardcoded-credential MinIO object store via an API that does not exist in
datafusion 41 (`object_store.AmazonS3Builder`), so it could never have run.
The engine now reads local Parquet files only; remote object-store support
should return alongside a real producer that writes Parquet to MinIO.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    import pyarrow as pa


class DataFusionEngine:
    """Runs analytical SQL against locally registered Parquet files."""

    def __init__(self) -> None:
        # pylint: disable-next=import-error
        import datafusion

        self._ctx = datafusion.SessionContext()

    def register_parquet_file(self, table_name: str, path: str | Path) -> None:
        """Expose a local Parquet file as the SQL table ``table_name``."""
        target = Path(path)
        if not target.exists():
            raise FileNotFoundError(f"Parquet file not found: {target}")
        self._ctx.register_parquet(table_name, str(target))

    def execute_sql(self, sql: str) -> "pa.Table":
        """Execute ``sql`` and return the result as an Arrow table."""
        import pyarrow as pa

        # datafusion 41 can emit result batches whose schemas disagree only
        # in nullability (e.g. COUNT(*) is not-null in data batches, nullable
        # in the empty trailing batch), which from_batches rejects. Normalize
        # every batch to the all-nullable schema before assembling the table.
        batches = self._ctx.sql(sql).collect()
        if not batches:
            return pa.table({})
        nullable_schema = pa.schema(
            [field.with_nullable(True) for field in batches[0].schema]
        )
        return pa.Table.from_batches(
            [batch.cast(nullable_schema) for batch in batches],
            schema=nullable_schema,
        )

    def execute_sql_to_polars(self, sql: str) -> Any:
        """Execute ``sql`` and return the result as a Polars DataFrame."""
        import polars as pl

        return pl.from_arrow(self.execute_sql(sql))


__all__ = ["DataFusionEngine"]
