"""Tests for the DataFusion local analytical SQL engine.

The engine runs SQL against local Parquet files without touching Postgres,
so every test here is a SimpleTestCase over a temporary directory — no
database, no network, no MinIO.
"""

from __future__ import annotations

import tempfile
from datetime import date
from pathlib import Path

from django.test import SimpleTestCase


def _write_sample_parquet(path: Path) -> None:
    import polars as pl

    df = pl.DataFrame(
        {
            "content_item_id": [1, 1, 2, 2, 3],
            "date": [
                date(2026, 6, 1),
                date(2026, 6, 2),
                date(2026, 6, 1),
                date(2026, 6, 2),
                date(2026, 6, 2),
            ],
            "clicks": [10, 50, 5, 6, 100],
        }
    )
    df.write_parquet(str(path))


class DataFusionEngineTests(SimpleTestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.parquet_path = Path(self._tmpdir.name) / "sample.parquet"
        _write_sample_parquet(self.parquet_path)

    def _engine(self):
        from apps.pipeline.services.datafusion_engine import DataFusionEngine

        engine = DataFusionEngine()
        engine.register_parquet_file("metrics", self.parquet_path)
        return engine

    def test_group_by_aggregation_returns_per_item_sums(self) -> None:
        table = self._engine().execute_sql(
            "SELECT content_item_id, SUM(clicks) AS total"
            " FROM metrics GROUP BY content_item_id ORDER BY content_item_id"
        )
        totals = dict(
            zip(
                table.column("content_item_id").to_pylist(),
                table.column("total").to_pylist(),
            )
        )
        self.assertEqual(totals, {1: 60, 2: 11, 3: 100})

    def test_date_filter_matches_single_day(self) -> None:
        table = self._engine().execute_sql(
            "SELECT COUNT(*) AS n FROM metrics WHERE \"date\" = DATE '2026-06-02'"
        )
        self.assertEqual(table.column("n").to_pylist(), [3])

    def test_execute_sql_to_polars_returns_dataframe(self) -> None:
        import polars as pl

        df = self._engine().execute_sql_to_polars(
            "SELECT content_item_id FROM metrics WHERE clicks > 40"
        )
        self.assertIsInstance(df, pl.DataFrame)
        self.assertEqual(sorted(df["content_item_id"].to_list()), [1, 3])

    def test_empty_result_set_has_zero_rows(self) -> None:
        table = self._engine().execute_sql(
            "SELECT content_item_id FROM metrics WHERE clicks > 10000"
        )
        self.assertEqual(table.num_rows, 0)

    def test_register_missing_file_raises_file_not_found(self) -> None:
        from apps.pipeline.services.datafusion_engine import DataFusionEngine

        engine = DataFusionEngine()
        with self.assertRaises(FileNotFoundError):
            engine.register_parquet_file(
                "ghost", Path(self._tmpdir.name) / "does-not-exist.parquet"
            )
