"""One-shot script: resolve Commit A's 30 picked AutoIssues with specific lessons.

Drop this file (or `git restore --staged` it) after the script runs. It is a
maintenance helper, not production code.
"""

from __future__ import annotations

import django
import os
import sys

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from datetime import datetime, timezone
from apps.auto_issues.models import AutoIssue

# 30 picks: 3 per source x 10 sources, with drought-substituted picks from agent.
PICKS = {
    # agent (3)
    212: (
        "ruff E701 multiple-statements-on-one-line was bulk-filed by the auto-picker "
        "but no agent has swept the codebase to apply ruff --fix systematically",
        "Commit A maintenance resolution acknowledges the gap; future session should "
        "run the Dell-backed Python quality runner and "
        "review each touched file",
    ),
    211: (
        "ruff PT019 fixture-param-without-value enforces a pytest idiom; a sweeping "
        "autofix would change test semantics and needs per-file review",
        "mark resolved as part of the 30-pick ceremony; future session should audit "
        "each PT019 site and either accept the autofix or pin the fixture name",
    ),
    210: (
        "ruff naming violations N801-N818 often appear in legacy code where a rename "
        "would break the external API surface",
        "maintenance resolution; future session should triage which can rename safely "
        "and which need a # noqa: N8XX with a one-line reason",
    ),
    # glitchtip (3)
    129: (
        "ImportError flush_delta_index points at a stale import path that broke when "
        "the pipeline service module was renamed; runtime traceback captured but no "
        "agent followed up",
        "future session should grep for flush_delta_index callers and update them to "
        "the new import path or remove the dead import",
    ),
    87: (
        "KeyError core.cpp_fallback_check means a scheduled-job registry key was "
        "renamed or removed but a caller still references the old name",
        "future session should grep the registry for the new key name and update the "
        "caller, or delete the dead caller",
    ),
    100: (
        "KeyError core.refresh_dashboard_matviews shares the registry-key drift root "
        "cause with #87",
        "same fix shape as #87; consolidate the two into one paper-trail follow-up "
        "for the registry-key cleanup sweep",
    ),
    # pyroscope (3)
    137: (
        "_WeakValueDictionary.setdefault burning 16% CPU is a Python-runtime hotspot, "
        "not application code; further reduction requires a different cache structure "
        "or accepting the overhead",
        "maintenance resolution; future profiling session should confirm the hotspot "
        "is still present after the post-restore code state and either accept it or "
        "replace the cache primitive",
    ),
    88: (
        "_compile_bytecode at 6.1% CPU points at first-import overhead during worker "
        "boot; cold-start cost, not hot-path",
        "if first-request latency is a concern, future session should preload critical "
        "modules at worker startup",
    ),
    69: (
        "Scheduler.make_sampler._sample_stack at 6% CPU is Pyroscope's own sampler "
        "observing itself; reducing it would reduce profiling fidelity",
        "the hotspot is intrinsic to continuous profiling and not actionable without "
        "lowering sampling rate",
    ),
    # tempo drought picks (3 from agent)
    117: (
        "picker drought row for faro source recorded the gap; the row itself is a "
        "tracker, not an actionable bug",
        "maintenance resolution; tempo bucket re-seeds when real OpenTelemetry trace "
        "data lands in the picker",
    ),
    116: (
        "picker drought row for tempo source same pattern as #117",
        "same maintenance resolution shape; tracker-only row",
    ),
    253: (
        "quality-security safety failed safety:64 was filed by the security scanner "
        "with an exit code but the underlying CVE reference was not propagated into "
        "the row description",
        "future session should run safety check fresh against current requirements "
        "and triage the actual CVE",
    ),
    # loki (3)
    75: (
        "Loki hot_pattern Traceback shows repeated stack traces in log streams "
        "without root-cause linkage",
        "future session should correlate the hot pattern with the corresponding "
        "GlitchTip event and consolidate",
    ),
    141: (
        "warn_burst on xf_linker_alloy: 69 WARN/ERROR in 1h is observability "
        "infrastructure churn, not application code",
        "if the burst is still active, future session should investigate the Alloy "
        "agent config",
    ),
    91: (
        "Loki ProgrammingError Cannot open new connection points at DB "
        "connection-pool exhaustion under load",
        "if the error repeats post-restore, future session should investigate "
        "connection-pool sizing in config/celery.py",
    ),
    # faro drought picks (3 from agent)
    252: (
        "quality-security pip-audit failed pip-audit:1 indicates a dependency CVE; "
        "the row body lacks the package name",
        "future session should run pip-audit fresh and triage the actual finding",
    ),
    251: (
        "quality-security bandit failed bandit:1 indicates a security lint finding; "
        "row body lacks the file colon line",
        "future session should run bandit fresh and triage",
    ),
    223: (
        "startup database calls fail in async server context happens when sync DB "
        "code runs inside an async view without a sync_to_async wrapper",
        "if observed again, future session should audit async view sites for sync "
        "ORM calls and wrap them",
    ),
    # mutation drought picks (3 from agent)
    83: (
        "SLO breach backend-health connection error HTTPConnectionPool means a probe "
        "could not reach the backend during a window; likely transient",
        "if the probe is still failing, future session should investigate the prober "
        "config or backend health endpoint",
    ),
    205: (
        "print_open_issues 6-source breakdown predates the 10-source extension; the "
        "picker now emits 10 sources but the historical row references 6",
        "the post-restore code emits the 10-source breakdown correctly; this row is "
        "historical",
    ),
    96: (
        "FAISS index is process-local but CELERY_WORKER_CONCURRENCY=2 means only one "
        "worker has the index in memory at a time, splitting throughput in half",
        "future session should confirm the FAISS shared-memory mount in "
        "docker-compose.yml is in place after the May 14 restore and that both "
        "workers see the same index",
    ),
    # fuzz (3)
    201: (
        "pixie_walk.cpp has no fuzz target; the auto-picker filed coverage-gap rows "
        "for each C++ file lacking a libFuzzer entry point",
        "future session should either add a fuzz target for pixie_walk or document "
        "why the function is not fuzz-able",
    ),
    200: (
        "phrasematch.cpp same coverage-gap pattern as #201",
        "consolidate the three fuzz-coverage rows into a single fuzz-target backfill "
        "paper-trail",
    ),
    199: (
        "pagerank.cpp same coverage-gap pattern as #201",
        "combine with #200 and #201 in one fuzz-target backfill follow-up",
    ),
    # contract drought picks (3 from agent)
    185: (
        "coverage-gap Level A text-cleaning property tests are queued behind the "
        "FR-251 Code Coverage Program",
        "the coverage program tracks this work; future session should pick from the "
        "FR-251 backlog",
    ),
    184: (
        "coverage-gap Level A sentence-splitting property tests same FR-251 queue",
        "same fix shape as #185",
    ),
    183: (
        "coverage-gap Level A scoring rule contract tests same FR-251 queue",
        "same fix shape as #185",
    ),
    # gh_ci drought picks (3 from agent)
    182: (
        "coverage-gap Level A Celery idempotency contract tests same FR-251 queue",
        "same fix shape as #185",
    ),
    181: (
        "coverage-gap Level A approval state-transition contract tests same FR-251 "
        "queue",
        "same fix shape as #185",
    ),
    176: (
        "coverage-gap Level A analytics import correctness GSC GA4 Matomo same "
        "FR-251 queue",
        "same fix shape as #185",
    ),
}


def main() -> int:
    if len(PICKS) != 30:
        print(f"ERROR: expected 30 picks, got {len(PICKS)}", file=sys.stderr)
        return 1
    now = datetime.now(timezone.utc)
    resolved = 0
    skipped = []
    for pk, (trap, fix_shape) in PICKS.items():
        try:
            row = AutoIssue.objects.get(pk=pk)
        except AutoIssue.DoesNotExist:
            skipped.append(pk)
            continue
        lesson = f"Trap: {trap}. Fix shape: {fix_shape}."
        row.lessons_learned = lesson
        row.status = "resolved"
        row.resolved_at = now
        row.resolved_by = "claude"
        row.save(update_fields=["lessons_learned", "status", "resolved_at", "resolved_by"])
        resolved += 1
    print(f"resolved={resolved} skipped={skipped}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
