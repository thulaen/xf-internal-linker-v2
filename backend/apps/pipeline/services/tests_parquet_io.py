"""Tests for the atomic Parquet writer, incl. the zstd compression codec.

Pure ``SimpleTestCase`` over a temp dir — no database, no network. The
codec assertion reads the Parquet file's column-chunk metadata back via
pyarrow so we prove the bytes on disk are genuinely ZSTD-compressed, not
just that the call did not raise.
"""

from __future__ import annotations

import tempfile
from pathlib import Path

from django.test import SimpleTestCase


class WriteParquetAtomicTests(SimpleTestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmpdir.cleanup)
        self.path = Path(self._tmpdir.name) / "snap.parquet"

    def _frame(self):
        import polars as pl

        return pl.DataFrame({"a": [1, 2, 3], "b": ["x", "y", "z"]})

    def test_round_trips_values(self) -> None:
        from apps.pipeline.services._parquet_io import write_parquet_atomic
        import polars as pl

        write_parquet_atomic(self._frame(), self.path)
        read_back = pl.read_parquet(str(self.path))
        self.assertEqual(read_back["a"].to_list(), [1, 2, 3])
        self.assertEqual(read_back["b"].to_list(), ["x", "y", "z"])

    def test_uses_zstd_compression_codec(self) -> None:
        import pyarrow.parquet as pq

        from apps.pipeline.services._parquet_io import write_parquet_atomic

        write_parquet_atomic(self._frame(), self.path)
        meta = pq.ParquetFile(str(self.path)).metadata
        codecs = {
            meta.row_group(rg).column(col).compression
            for rg in range(meta.num_row_groups)
            for col in range(meta.num_columns)
        }
        self.assertEqual(codecs, {"ZSTD"})

    def test_no_tmp_file_left_after_success(self) -> None:
        from apps.pipeline.services._parquet_io import write_parquet_atomic

        write_parquet_atomic(self._frame(), self.path)
        self.assertTrue(self.path.exists())
        self.assertFalse(self.path.with_suffix(".parquet.tmp").exists())
