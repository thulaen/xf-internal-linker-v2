"""Parity tests for the Polars-backed CSV streaming helper in apps.graph.views.

The new ``_polars_chunked_csv`` replaces a per-row ``csv.writer`` loop. These
tests pin its byte output against Python's ``csv.writer`` so a future change to
the helper that drifts from the legacy format is caught immediately.
"""

from __future__ import annotations

import csv
import io

from django.test import SimpleTestCase

from apps.graph.views import _polars_chunked_csv


def _legacy_writerow_bytes(rows: list[dict], columns: list[str]) -> str:
    """Build the same CSV that the pre-Polars ``csv.writer`` block would have."""
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(columns)
    for row in rows:
        writer.writerow([row.get(col) if row.get(col) is not None else "" for col in columns])
    return buf.getvalue()


class PolarsChunkedCsvParityTests(SimpleTestCase):
    """Output of ``_polars_chunked_csv`` must equal the legacy csv.writer output."""

    def _drain(self, gen) -> str:
        return "".join(list(gen))

    def test_empty_input_emits_only_header(self):
        cols = ["id", "name"]
        out = self._drain(_polars_chunked_csv(iter([]), cols))
        legacy = _legacy_writerow_bytes([], cols)
        self.assertEqual(out, legacy)

    def test_single_row(self):
        cols = ["id", "name", "score"]
        rows = [{"id": 1, "name": "alpha", "score": 0.5}]
        out = self._drain(_polars_chunked_csv(iter(rows), cols))
        legacy = _legacy_writerow_bytes(rows, cols)
        self.assertEqual(out, legacy)

    def test_multiple_rows_no_chunk_boundary(self):
        cols = ["id", "name"]
        rows = [{"id": i, "name": f"item-{i}"} for i in range(10)]
        out = self._drain(_polars_chunked_csv(iter(rows), cols, chunk_size=250))
        legacy = _legacy_writerow_bytes(rows, cols)
        self.assertEqual(out, legacy)

    def test_chunked_output_concatenated_matches_legacy(self):
        """When the chunk_size is small, the helper yields multiple chunks; the
        concatenation must still match the legacy single-pass csv.writer output."""
        cols = ["id", "name"]
        rows = [{"id": i, "name": f"item-{i}"} for i in range(25)]
        out = self._drain(_polars_chunked_csv(iter(rows), cols, chunk_size=5))
        legacy = _legacy_writerow_bytes(rows, cols)
        self.assertEqual(out, legacy)

    def test_value_with_comma_is_quoted(self):
        cols = ["id", "name"]
        rows = [{"id": 1, "name": "has, a comma"}]
        out = self._drain(_polars_chunked_csv(iter(rows), cols))
        legacy = _legacy_writerow_bytes(rows, cols)
        self.assertEqual(out, legacy)

    def test_value_with_quote_is_doubled(self):
        cols = ["id", "name"]
        rows = [{"id": 1, "name": 'has "quote" inside'}]
        out = self._drain(_polars_chunked_csv(iter(rows), cols))
        legacy = _legacy_writerow_bytes(rows, cols)
        self.assertEqual(out, legacy)

    def test_none_values_become_empty_string(self):
        cols = ["id", "notes"]
        rows = [{"id": 1, "notes": None}, {"id": 2, "notes": "set"}]
        out = self._drain(_polars_chunked_csv(iter(rows), cols))
        legacy = _legacy_writerow_bytes(rows, cols)
        self.assertEqual(out, legacy)

    def test_crlf_line_terminator(self):
        cols = ["id"]
        rows = [{"id": 1}, {"id": 2}]
        out = self._drain(_polars_chunked_csv(iter(rows), cols))
        # Should use CRLF (\r\n) like the legacy csv.writer default.
        self.assertIn("\r\n", out)
        # Each non-trailing line ends with CRLF.
        lines = out.splitlines(keepends=True)
        for line in lines:
            self.assertTrue(line.endswith("\r\n"), f"line not CRLF: {line!r}")

    def test_header_only_in_first_chunk(self):
        """Verify chunked yields don't repeat the header in subsequent chunks."""
        cols = ["id"]
        rows = [{"id": i} for i in range(15)]
        chunks = list(_polars_chunked_csv(iter(rows), cols, chunk_size=5))
        # First chunk is the header; subsequent chunks are 5-row data each, no repeated header.
        self.assertEqual(chunks[0], "id\r\n")
        for chunk in chunks[1:]:
            self.assertFalse(chunk.startswith("id\r\n"), f"chunk repeats header: {chunk!r}")

    def test_parity_against_legacy_random_input(self):
        import random

        rng = random.Random(7)
        cols = ["id", "title", "score", "notes"]
        rows = []
        for _ in range(500):
            rows.append(
                {
                    "id": rng.randrange(1_000_000),
                    "title": rng.choice(["alpha", "beta, with comma", 'has "quote"', "plain", ""]),
                    "score": round(rng.random(), 3),
                    "notes": None if rng.random() < 0.2 else "ok",
                },
            )
        out = self._drain(_polars_chunked_csv(iter(rows), cols, chunk_size=37))
        legacy = _legacy_writerow_bytes(rows, cols)
        self.assertEqual(out, legacy)
