"""Record Rust Criterion benchmark results into BenchmarkResult.

Why this command exists:
  Rust kernels build and benchmark on the Dell helper, not in the backend
  container (the container cannot reach Dell's Docker). So benchmarking is a
  two-step hand-off: the host script ``scripts/bench_rust_on_dell.py`` runs
  ``cargo bench`` on Dell, parses Criterion's nanosecond estimates, and writes
  a JSON list; THIS command (running in the backend container, which has the
  database) ingests that JSON into ``BenchmarkResult`` rows tagged
  ``language="rust"``. The performance-regression gate then reads this history.

Input JSON: a list of objects with at least
  {"extension": "scoring", "function_name": "bench_score",
   "input_size": "100", "mean_ns": 1234, "median_ns": 1200}
optional: "items_per_second", "threshold_ns".
"""

from __future__ import annotations

import json

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

_REQUIRED = ("extension", "function_name", "input_size", "mean_ns")


class Command(BaseCommand):
    help = "Ingest host-produced Criterion results into BenchmarkResult (language=rust)."

    def add_arguments(self, parser):
        parser.add_argument("--json", required=True, help="Path to the Criterion results JSON list.")
        parser.add_argument("--trigger", default="scheduled", help="BenchmarkRun trigger label.")
        parser.add_argument(
            "--dry-run", action="store_true",
            help="Parse and report counts without writing any rows.",
        )

    def handle(self, *args, **options):
        from apps.benchmarks.models import BenchmarkResult, BenchmarkRun
        from apps.benchmarks.services.runner import classify_results
        from apps.benchmarks.tasks import _summarise_results

        rows = self._load(options["json"])
        results = [self._to_result(BenchmarkResult, row, i) for i, row in enumerate(rows)]
        classify_results(results)

        if options["dry_run"]:
            self.stdout.write(
                f"[DRY RUN] parsed {len(results)} rust benchmark result(s); nothing written."
            )
            return

        run = BenchmarkRun.objects.create(trigger=options["trigger"])
        for r in results:
            r.run = run
        BenchmarkResult.objects.bulk_create(results)
        run.summary_json = _summarise_results(results)
        run.status = "completed"
        run.finished_at = timezone.now()
        run.save()
        self.stdout.write(
            f"[RUST BENCHMARKS RECORDED: run=#{run.pk} results={len(results)}]"
        )

    @staticmethod
    def _load(path: str) -> list:
        try:
            with open(path, encoding="utf-8") as fh:
                data = json.load(fh)
        except (OSError, json.JSONDecodeError) as exc:
            raise CommandError(f"cannot read results JSON {path!r}: {exc}") from exc
        if not isinstance(data, list) or not data:
            raise CommandError("results JSON must be a non-empty list of result objects")
        return data

    @staticmethod
    def _to_result(model, row: dict, index: int):
        missing = [k for k in _REQUIRED if k not in row]
        if missing:
            raise CommandError(f"result #{index} missing required field(s): {missing}")
        return model(
            language="rust",
            extension=str(row["extension"]),
            function_name=str(row["function_name"]),
            input_size=str(row["input_size"]),
            mean_ns=int(row["mean_ns"]),
            median_ns=int(row.get("median_ns", row["mean_ns"])),
            items_per_second=float(row.get("items_per_second", 0.0)),
            threshold_ns=row.get("threshold_ns"),
        )
