"""manage.py record_perf_baseline — store a function's perf baseline."""

from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.paper_trail.services import lesson_index as svc


class Command(BaseCommand):
    help = "Record a perf baseline for a function in the PerfBaselineCache."

    def add_arguments(self, parser):
        parser.add_argument("--function", required=True,
                            help="Canonical function signature (module.path.fn).")
        parser.add_argument("--p50-ns", type=int, required=True)
        parser.add_argument("--p95-ns", type=int, required=True)
        parser.add_argument("--p99-ns", type=int, required=True)
        parser.add_argument("--mean-ns", type=int, default=0,
                            help="Mean nanoseconds; defaults to p50 if omitted.")
        parser.add_argument("--samples", type=int, default=100)

    def handle(self, *args, **opts):
        mean = opts["mean_ns"] or opts["p50_ns"]
        ok = svc.perf_put(
            opts["function"],
            p50_ns=opts["p50_ns"],
            p95_ns=opts["p95_ns"],
            p99_ns=opts["p99_ns"],
            mean_ns=mean,
            samples=opts["samples"],
        )
        if not ok:
            self.stderr.write(
                "FAIL record_perf_baseline: PerfBaselineCache is full. "
                "Run `manage.py prune_test_artefacts --prefix perf` to reclaim, "
                "or increase the cache cap in services/lesson_index.py.\n"
            )
            raise SystemExit(2)
        self.stdout.write(
            f"[PERF BASELINE RECORDED: function={opts['function']} "
            f"p50_ns={opts['p50_ns']} samples={opts['samples']}]"
        )
