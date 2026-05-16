"""manage.py verify_perf_speedup — compute speedup vs baseline.

Emits either:
  [PERFORMANCE PROOF: function=<fn> baseline_ns=X post_ns=Y speedup=Z.ZZx iterations=N/10]
  [PERFORMANCE EXEMPTION: function=<fn> best_achieved=X.YYx iterations=N/10 reason="..."]
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from apps.paper_trail.services import lesson_index as svc


_TARGET_SPEEDUP = 20.0


class Command(BaseCommand):
    help = "Compute speedup of a function vs its stored baseline."

    def add_arguments(self, parser):
        parser.add_argument("--function", required=True)
        parser.add_argument("--new-p50-ns", type=int, required=True)
        parser.add_argument("--iterations", type=int, default=1,
                            help="How many optimisation passes were attempted.")
        parser.add_argument("--exemption-reason", default="",
                            help="If speedup < 20x and 10 iterations exhausted, provide reason.")

    def handle(self, *args, **opts):
        fn = opts["function"]
        new_p50 = opts["new_p50_ns"]
        speedup = svc.compute_speedup(fn, new_p50_ns=new_p50)
        if speedup is None:
            raise CommandError(
                f"FAIL verify_perf_speedup: no baseline for {fn}. "
                f"Run `manage.py record_perf_baseline --function {fn} ...` first."
            )
        baseline = svc.perf_get(fn)["p50_ns"]
        iterations = max(1, int(opts["iterations"]))

        if speedup >= _TARGET_SPEEDUP:
            self.stdout.write(
                f"[PERFORMANCE PROOF: function={fn} baseline_ns={baseline} "
                f"post_ns={new_p50} speedup={speedup:.2f}x iterations={iterations}/10]"
            )
            return

        reason = opts["exemption_reason"].strip()
        if not reason:
            raise CommandError(
                f"FAIL verify_perf_speedup: speedup is {speedup:.2f}x — below "
                f"the 20x target. After up to 10 iterations of optimisation, "
                f"if you still cannot reach 20x, supply --exemption-reason "
                f"with a plain-English explanation citing one of: I/O bound, "
                f"algorithmic optimality, hardware-bound, already-vectorised, "
                f"external-API rate-limit, single-instruction hot loop, "
                f"dataset too small to amortise."
            )

        self.stdout.write(
            f"[PERFORMANCE EXEMPTION: function={fn} best_achieved={speedup:.2f}x "
            f'iterations={iterations}/10 reason="{reason}"]'
        )
