"""One-time backfill: acknowledge ErrorLog rows whose underlying audit now passes.

Usage:
    docker compose exec -T backend python manage.py acknowledge_resolved_warnings

What this fixes:
    Before 2026-05-10 the boot-time NO-DUPLICATES audit fired six
    "no-dups invariant" warnings on every backend boot. Each warning
    landed as a row in `audit_errorlog` with `job_type='startup_smoke_test'`.
    After 134 boots that's six rows with `occurrence_count=134` cluttering
    `/error-log` forever — even though the underlying issue has been
    resolved by today's migrations.

    `run_startup_smoke_tests()` was extended (same change) to auto-mark
    these stale rows acknowledged on every subsequent boot. This command
    runs the same logic ONCE so the operator doesn't have to wait for the
    next backend restart.

Idempotent: re-running is harmless. The acknowledge SQL is a no-op when
nothing matches.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from apps.core.services.self_test_smoke import (
    _auto_acknowledge_resolved_smoke_warnings,
    run_startup_smoke_tests,
)


class Command(BaseCommand):
    help = "Acknowledge stale ErrorLog rows whose underlying audit now passes."

    def handle(self, *args, **options):
        # 1. Run the audit once to compute the set of CURRENTLY flagged
        #    steps. The smoke-test side-effect already calls the
        #    auto-acknowledge function, but we re-compute the count
        #    here so the user can see what was changed.
        warnings = run_startup_smoke_tests()
        self.stdout.write(
            f"  Currently flagged warnings: {len(warnings)}"
        )

        # 2. Run the auto-acknowledge once more with an empty
        #    currently_flagged set to surface any rows the side-effect
        #    pass missed (e.g. job_type='startup_smoke_test' rows whose
        #    step name doesn't match any current rule).
        from apps.audit.models import ErrorLog

        before = ErrorLog.objects.filter(
            job_type="startup_smoke_test", acknowledged=False
        ).count()
        flagged_steps = {
            line.split(" ")[2] for line in warnings if "New table" in line
        }
        acked = _auto_acknowledge_resolved_smoke_warnings(flagged_steps)
        after = ErrorLog.objects.filter(
            job_type="startup_smoke_test", acknowledged=False
        ).count()
        self.stdout.write(
            self.style.SUCCESS(
                f"  Acknowledged {acked} stale row(s). Open rows: {before} -> {after}."
            )
        )
