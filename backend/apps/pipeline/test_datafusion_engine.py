from __future__ import annotations

import tempfile
from pathlib import Path

import polars as pl
import pyarrow as pa
import pyarrow.parquet as pq
from django.test import SimpleTestCase

from apps.pipeline.services.datafusion_engine import DataFusionEngine


class DataFusionEngineTests(SimpleTestCase):
    def setUp(self) -> None:
        # Create a temporary directory for Parquet files
        self.tmpdir = tempfile.TemporaryDirectory()
        self.tmp_path = Path(self.tmpdir.name)
        
        self.engine = DataFusionEngine()
        
        # Create a sample table:
        # 10 rows, columns: 'id' (int), 'value' (str), 'score' (float)
        self.table = pa.table({
            "id": [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
            "value": ["a", "b", "c", "a", "b", "c", "a", "b", "c", "d"],
            "score": [1.1, 2.2, 3.3, 4.4, 5.5, 6.6, 7.7, 8.8, 9.9, 10.0]
        })
        self.parquet_path = self.tmp_path / "sample.parquet"
        pq.write_table(self.table, self.parquet_path)
        
        # Empty table
        self.empty_table = pa.schema([
            pa.field("id", pa.int64()),
            pa.field("value", pa.string()),
        ]).empty_table()
        self.empty_parquet_path = self.tmp_path / "empty.parquet"
        pq.write_table(self.empty_table, self.empty_parquet_path)

    def tearDown(self) -> None:
        self.tmpdir.cleanup()

    def test_register_parquet_file_success_string_path(self) -> None:
        """Test registering a Parquet file using a string path."""
        self.engine.register_parquet_file("str_table", str(self.parquet_path))
        res = self.engine.execute_sql("SELECT COUNT(*) as cnt FROM str_table")
        self.assertEqual(res.column("cnt").to_pylist(), [10])

    def test_register_parquet_file_success_pathlib_path(self) -> None:
        """Test registering a Parquet file using a pathlib.Path."""
        self.engine.register_parquet_file("path_table", self.parquet_path)
        res = self.engine.execute_sql("SELECT COUNT(*) as cnt FROM path_table")
        self.assertEqual(res.column("cnt").to_pylist(), [10])

    def test_register_parquet_file_not_found(self) -> None:
        """Test that registering a non-existent file raises FileNotFoundError."""
        with self.assertRaises(FileNotFoundError) as cm:
            self.engine.register_parquet_file("missing", self.tmp_path / "does_not_exist.parquet")
        self.assertIn("Parquet file not found", str(cm.exception))

    def test_execute_sql_basic_filtering(self) -> None:
        """Test executing a basic SQL query with filtering."""
        self.engine.register_parquet_file("sample", self.parquet_path)
        res = self.engine.execute_sql("SELECT id, value FROM sample WHERE id > 8 ORDER BY id")
        self.assertEqual(res.num_rows, 2)
        self.assertEqual(res.column("id").to_pylist(), [9, 10])
        self.assertEqual(res.column("value").to_pylist(), ["c", "d"])

    def test_execute_sql_aggregation_nullability_fix(self) -> None:
        """
        Test that execute_sql properly normalizes schemas across batches.
        A COUNT(*) aggregation can sometimes produce batches with mismatched
        nullability in datafusion. We ensure it works without throwing Arrow errors.
        """
        self.engine.register_parquet_file("sample", self.parquet_path)
        res = self.engine.execute_sql("SELECT value, COUNT(*) as cnt FROM sample GROUP BY value ORDER BY value")
        
        self.assertEqual(res.num_rows, 4)
        self.assertEqual(res.column("value").to_pylist(), ["a", "b", "c", "d"])
        self.assertEqual(res.column("cnt").to_pylist(), [3, 3, 3, 1])
        
        # Verify that the schema is nullable (as forced by the wrapper).
        for field in res.schema:
            self.assertTrue(field.nullable)

    def test_execute_sql_empty_result_from_query(self) -> None:
        """Test a query that yields zero rows from a populated table."""
        self.engine.register_parquet_file("sample", self.parquet_path)
        res = self.engine.execute_sql("SELECT * FROM sample WHERE id > 100")
        self.assertEqual(res.num_rows, 0)
        # Should retain schema of the table
        self.assertTrue(res.schema is not None)

    def test_execute_sql_on_empty_table(self) -> None:
        """Test querying a completely empty Parquet file."""
        self.engine.register_parquet_file("empty_tbl", self.empty_parquet_path)
        res = self.engine.execute_sql("SELECT * FROM empty_tbl")
        self.assertEqual(res.num_rows, 0)

    def test_execute_sql_syntax_error(self) -> None:
        """Test that invalid SQL raises an exception from datafusion."""
        with self.assertRaises(Exception):
            self.engine.execute_sql("SELECT * FROOOOM missing_table")

    def test_execute_sql_to_polars(self) -> None:
        """Test executing a query and converting the result directly to a Polars DataFrame."""
        self.engine.register_parquet_file("sample", self.parquet_path)
        df = self.engine.execute_sql_to_polars("SELECT id, score FROM sample WHERE value = 'a' ORDER BY id")
        
        self.assertIsInstance(df, pl.DataFrame)
        self.assertEqual(len(df), 3)
        self.assertEqual(df["id"].to_list(), [1, 4, 7])
        self.assertEqual(df["score"].to_list(), [1.1, 4.4, 7.7])
