"""manage.py log_performance_exemption — file a perf_exemption AutoIssue."""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from apps.auto_issues.models import AutoIssue


class Command(BaseCommand):
    help = "Log that a function couldn't reach 20x speedup after 10 iterations."

    def add_arguments(self, parser):
        parser.add_argument("--function", required=True)
        parser.add_argument("--reason", required=True,
                            help="Plain-English explanation (one of the accepted categories).")
        parser.add_argument("--best-achieved", type=float, required=True,
                            help="Best speedup ratio reached, e.g. 3.5 for 3.5x.")
        parser.add_argument("--iterations", type=int, default=10)

    def handle(self, *args, **opts):
        fn = opts["function"]
        reason = opts["reason"].strip()
        best = float(opts["best_achieved"])
        iterations = int(opts["iterations"])
        if len(reason) < 20:
            raise CommandError(
                "FAIL log_performance_exemption: reason is shorter than 20 "
                "characters. Provide a substantive explanation citing one of: "
                "I/O bound, algorithmic optimality, hardware-bound, "
                "already-vectorised, external-API rate-limit, single-instruction "
                "hot loop, dataset too small to amortise."
            )
        title = f"[perf_exemption] {fn}: best {best:.2f}x after {iterations} iterations"
        description = (
            f"Function: {fn}\n"
            f"Best speedup achieved: {best:.2f}x\n"
            f"Iterations tried: {iterations}/10\n"
            f"Reason: {reason}\n"
        )
        ai = AutoIssue.objects.create(
            source=AutoIssue.SOURCE_AGENT,
            external_id=f"perf_exemption::{fn}",
            fingerprint=f"perf_exemption_{abs(hash(fn)) % (10 ** 12):012d}",
            title=title[:512],
            description=description,
            severity=AutoIssue.SEVERITY_MEDIUM,
            status=AutoIssue.STATUS_OPEN,
            occurrence_count=1,
            last_seen=timezone.now(),
        )
        self.stdout.write(
            f"[PERF EXEMPTION LOGGED: AutoIssue=#{ai.pk} function={fn} "
            f"best={best:.2f}x reason=\"{reason[:60]}\"]"
        )
