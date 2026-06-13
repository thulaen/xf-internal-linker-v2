"""Tests for the record_rust_benchmarks management command."""

from __future__ import annotations

import json
import tempfile
from io import StringIO
from pathlib import Path

from django.core.management import CommandError, call_command
from django.test import TestCase

from apps.benchmarks.models import BenchmarkResult, BenchmarkRun


def _write(rows) -> str:
    tmp = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump(rows, tmp)
    tmp.close()
    return tmp.name

_ROWS = [
    {"extension": "scoring", "function_name": "bench_score", "input_size": "100",
     "mean_ns": 1234, "median_ns": 1200, "items_per_second": 81000.0},
    {"extension": "texttok", "function_name": "bench_tokenize", "input_size": "10000",
     "mean_ns": 50000},
]


class RecordRustBenchmarksTests(TestCase):
    def test_records_rows_and_creates_completed_run(self) -> None:
        path = _write(_ROWS)
        out = StringIO()
        call_command("record_rust_benchmarks", "--json", path, "--trigger", "manual", stdout=out)
        self.assertIn("RUST BENCHMARKS RECORDED", out.getvalue())
        run = BenchmarkRun.objects.latest("started_at")
        self.assertEqual(run.status, "completed")
        self.assertEqual(run.summary_json["total"], 2)
        self.assertEqual(run.summary_json["languages"]["rust"], 2)
        rows = BenchmarkResult.objects.filter(run=run)
        self.assertEqual(rows.count(), 2)
        self.assertTrue(all(r.language == "rust" for r in rows))
        scoring = rows.get(extension="scoring")
        self.assertEqual(scoring.mean_ns, 1234)
        self.assertEqual(scoring.median_ns, 1200)

    def test_median_defaults_to_mean_when_absent(self) -> None:
        path = _write(_ROWS)
        call_command("record_rust_benchmarks", "--json", path, stdout=StringIO())
        texttok = BenchmarkResult.objects.get(extension="texttok")
        self.assertEqual(texttok.median_ns, 50000)

    def test_dry_run_writes_nothing(self) -> None:
        path = _write(_ROWS)
        out = StringIO()
        call_command("record_rust_benchmarks", "--json", path, "--dry-run", stdout=out)
        self.assertIn("DRY RUN", out.getvalue())
        self.assertEqual(BenchmarkRun.objects.count(), 0)
        self.assertEqual(BenchmarkResult.objects.count(), 0)

    def test_missing_required_field_raises(self) -> None:
        path = _write([{"extension": "x", "function_name": "y"}])  # no input_size/mean_ns
        with self.assertRaises(CommandError):
            call_command("record_rust_benchmarks", "--json", path, stdout=StringIO())

    def test_empty_list_raises(self) -> None:
        path = _write([])
        with self.assertRaises(CommandError):
            call_command("record_rust_benchmarks", "--json", path, stdout=StringIO())

    def test_unreadable_path_raises(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "record_rust_benchmarks",
                "--json", str(Path(tempfile.gettempdir()) / "nope-does-not-exist.json"),
                stdout=StringIO(),
            )
