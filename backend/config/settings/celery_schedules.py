"""
Celery Beat schedule definitions.

Extracted from base.py to keep file length under the 500-line lint limit.
Imported by base.py via: from .celery_schedules import CELERY_BEAT_SCHEDULE
"""

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # ── Embedding health & quality (plan Parts 3 + 4) ─────────────────
    # Fortnightly accuracy audit — Thursdays 13:00 UTC, in the Medium window.
    # Task respects the 13-day fortnight gate + 11:00-22:59 UTC window guard
    # internally (per apps/scheduled_updates/window.py), so double-dispatches
    # by Beat are trivially idempotent.
    "fortnightly-embedding-accuracy": {
        "task": "pipeline.embedding_accuracy_audit",
        "schedule": crontab(minute=0, hour=13, day_of_week=4),
        "options": {"queue": "pipeline"},
        "kwargs": {"fortnightly": True},
    },
    # Monthly provider bake-off — 1st of each month at 14:30 UTC, after
    # monthly full-sync tasks complete. Scores local + OpenAI + Gemini on
    # the user's approved/rejected Suggestion qrels.
    "monthly-embedding-bakeoff": {
        "task": "pipeline.embedding_provider_bakeoff",
        "schedule": crontab(minute=30, hour=14, day_of_month=1),
        "options": {"queue": "pipeline"},
    },
    # ── Scheduled Updates orchestrator (PR-B) — 11am-11pm serial runner.
    # Window widened from 13-23 → 11-23 on 2026-04-25 to give the
    # operator two extra hours of daily capacity. Fires every 5 minutes
    # inside the 11:00-22:59 window. Each tick is idempotent: if the
    # Redis lock is held or no pending job fits the window, the task
    # exits silently. The catch-up sweep (which raises deduped
    # missed-job alerts) runs on every tick — including ticks that
    # skip because of the window guard — so a job that missed
    # yesterday's window still surfaces as an alert the moment the
    # runner wakes up next morning.
    "scheduled-updates-runner-tick": {
        "task": "scheduled_updates.run_next_scheduled_job",
        "schedule": crontab(hour="11-22", minute="*/5"),
        "options": {"queue": "default", "expires": 290},
    },
    # Stalled-job detector: every hour inside the window. Raises a
    # STALLED alert for any RUNNING job whose started_at is more than
    # 4 h ago. Does NOT flip state — operator decides whether to
    # pause/cancel via the API.
    "scheduled-updates-detect-stalled": {
        "task": "scheduled_updates.detect_stalled_jobs",
        "schedule": crontab(hour="11-22", minute=30),
        "options": {"queue": "default", "expires": 3500},
    },
    # Nightly (late-window) prune of resolved JobAlert rows older than
    # 30 days — keeps the history tab bounded without dropping recent
    # resolves. Runs at 22:45 so it's the last thing the window does.
    "scheduled-updates-prune-resolved-alerts": {
        "task": "scheduled_updates.prune_resolved_alerts",
        "schedule": crontab(hour=22, minute=45),
        "options": {"queue": "default"},
    },
    # ── Heavy tasks: 13:00–13:30 UTC daytime window ─────────────────
    # Moved from the 21:00-22:00 UTC evening window to 13:00-13:30 UTC so
    # tasks actually run on a laptop that's off overnight. Trade-off: heavy
    # jobs may contend with the operator's Chrome/dev work during the
    # afternoon; see docs/PERFORMANCE.md §5 for the old rationale.
    "nightly-xenforo-sync": {
        "task": "pipeline.import_content",
        "schedule": crontab(hour=13, minute=0),
        "kwargs": {"source": "api", "mode": "full"},
        "options": {"queue": "pipeline"},
    },
    # Part 6.5 — monthly baseline refresh: 1st of every month.
    # Forces a full re-embedding to ensure zero drift from live sites.
    # Separated from monthly-python-weight-tune to avoid slot collision.
    "monthly-xenforo-full-sync": {
        "task": "pipeline.import_content",
        "schedule": crontab(hour=13, minute=30, day_of_month="1"),
        "kwargs": {"source": "api", "mode": "full", "force_reembed": True},
        "options": {"queue": "pipeline"},
    },
    "monthly-wordpress-full-sync": {
        "task": "pipeline.import_content",
        "schedule": crontab(hour=14, minute=0, day_of_month="1"),
        "kwargs": {"source": "wp", "mode": "full", "force_reembed": True},
        "options": {"queue": "pipeline"},
    },
    # ── Medium tasks: 13:30–13:45 UTC ───────────────────────────────
    # FR-018 — monthly auto-tuner: 13:45 UTC on the first Sunday of every month.
    "monthly-python-weight-tune": {
        "task": "pipeline.monthly_weight_tune",
        "schedule": crontab(hour=13, minute=45, day_of_week=0, day_of_month="1-7"),
        "options": {"queue": "pipeline"},
    },
    # FR-018b — monthly meta-algorithm autotuner: 14:15 UTC on the first
    # Sunday of every month (30 min after the FR-018 ranking-weight tuner
    # so the two don't contend for the same Postgres write window).
    "monthly-python-meta-tune": {
        "task": "pipeline.monthly_meta_tune",
        "schedule": crontab(hour=14, minute=15, day_of_week=0, day_of_month="1-7"),
        "options": {"queue": "pipeline"},
    },
    # FR-025 — weekly session co-occurrence rebuild: Monday 13:30 UTC.
    "weekly-session-cooccurrence": {
        "task": "cooccurrence.compute_session_cooccurrence",
        "schedule": crontab(hour=13, minute=30, day_of_week=1),
        "options": {"queue": "default"},
    },
    # ── Light tasks: 14:00–14:30 UTC ────────────────────────────────
    # FR-018 — weekly GSC rollback check: Sunday 14:00 UTC.
    "weekly-weight-rollback-check": {
        "task": "pipeline.check_weight_rollback",
        "schedule": crontab(hour=14, minute=0, day_of_week=0),
        "options": {"queue": "pipeline"},
    },
    # Part 7 — data retention is now scheduled via the @scheduled_job
    # decorator in apps/scheduled_updates/jobs.py at daily 22:30 inside
    # the 11am-11pm operator window. The scheduler runner picks it up,
    # honours pause/resume, surfaces missed runs as deduped alerts, and
    # publishes Roaring-bitmap cardinality previews to the dashboard.
    # The celery beat entry is intentionally absent — the function
    # ``apps.pipeline.tasks.nightly_data_retention`` is still
    # invocable manually via ``.run()`` from the diagnostics page.
    # Stuck job cleanup: 14:10 UTC daily.
    "cleanup-stuck-sync-jobs": {
        "task": "pipeline.cleanup_stuck_sync_jobs",
        "schedule": crontab(hour=14, minute=10),
        "options": {"queue": "pipeline"},
    },
    # Part 9 — 12-week self-pruning: Sunday 14:15 UTC.
    "12-week-prune-stale-data": {
        "task": "pipeline.prune_stale_data",
        "schedule": crontab(hour=14, minute=15, day_of_week=0),
        "options": {"queue": "pipeline", "expires": 3600},
    },
    # Gap 3 — weekly reviewer scorecard computation: Monday 14:00 UTC.
    "weekly-reviewer-scorecard": {
        "task": "audit.compute_weekly_reviewer_scorecard",
        "schedule": crontab(hour=14, minute=0, day_of_week=1),
        "options": {"queue": "default"},
    },
    # Phase GT Step 7 — GlitchTip issue sync every 30 minutes during the
    # active-laptop window (11:00–23:00 UTC). Outside that window the
    # laptop is likely off, so a 30-min interval would just queue tasks
    # that fire as a storm at next boot. Cron-based scheduling avoids
    # that. Expires at 29 min so a stuck run can't overlap the next one.
    "glitchtip-issue-sync": {
        "task": "audit.sync_glitchtip_issues",
        "schedule": crontab(hour="11-23", minute="0,30"),
        "options": {"queue": "default", "expires": 1700},
    },
    # OPT-84 — daily performance benchmarks: 14:15 UTC.
    "nightly-benchmarks": {
        "task": "apps.benchmarks.tasks.run_all_benchmarks",
        "schedule": crontab(hour=14, minute=15),
        "kwargs": {"trigger": "scheduled"},
        "options": {"queue": "default"},
    },
    # Auto-issues picker chain inside the active-laptop window
    # (11:00–23:00 UTC). The laptop is likely OFF outside that window,
    # so cron firing at 04:00 just queues tasks that storm-fire at next
    # boot. See docs/CPP-DAILY-ISSUE-PICKER-SPEC.md for math.
    #
    # GlitchTip picker bumped to every 30 min (2026-05-10) so the
    # session-start ritual sees fresh data. Picker is a pure DB job
    # (~0.4 s per run on 89 unacked errors) and idempotent — upserts via
    # the (source, external_id) unique constraint. Staggered 5 minutes
    # after `audit.sync_glitchtip_issues` (at :00,:30) so the mirror is
    # always populated before the picker reads it.
    "auto-issues-glitchtip-pick": {
        "task": "auto_issues.pick_daily_glitchtip_issues",
        "schedule": crontab(hour="11-23", minute="5,35"),
        "options": {"queue": "default", "expires": 1500},
    },
    # Pyroscope picker bumped to every 30 min (2026-05-10) so the
    # session-start ritual sees fresh hotspots. Same-day hotspot
    # detector added per plan does-adding-qodana-make-swift-wall.md
    # Stream 2 — week-over-week regressions still gated on 7-day
    # warmup, but hotspots produce findings from day one. Staggered at
    # :10/:40 (5 min after picker chain at :05/:35) so Postgres isn't
    # contended.
    "auto-issues-pyroscope-pick": {
        "task": "auto_issues.pick_daily_pyroscope_regressions",
        "schedule": crontab(hour="11-23", minute="10,40"),
        "options": {"queue": "default", "expires": 1500},
    },
    # Loki picker added 2026-05-10 per plan
    # does-adding-qodana-make-swift-wall.md Stream 4. Mines
    # repeated WARN/ERROR patterns from Loki via LogQL and produces
    # source='loki' AutoIssues. Staggered at :15/:45 so it runs after
    # GlitchTip (:05/:35) and Pyroscope (:10/:40) — no Postgres
    # contention, no Loki contention either.
    "auto-issues-loki-pick": {
        "task": "auto_issues.pick_daily_loki_findings",
        "schedule": crontab(hour="11-23", minute="15,45"),
        "options": {"queue": "default", "expires": 1500},
    },
    # Faro picker added 2026-05-11 per plan
    # ~/.claude/plans/objective-deploy-and-integrate-zany-bee.md Stream 5.
    # Faro Web SDK ships browser RUM (JS errors + Web Vitals) through
    # Alloy into Loki labelled `source="faro"`. Picker queries those
    # streams via LogQL like the loki picker. Staggered at :20/:50 — 5
    # min after Loki (:15/:45) and 5 min before Tempo (:25/:55).
    "auto-issues-faro-pick": {
        "task": "auto_issues.pick_daily_faro_findings",
        "schedule": crontab(hour="11-23", minute="20,50"),
        "options": {"queue": "default", "expires": 1500},
    },
    # Tempo picker added 2026-05-11 per plan
    # ~/.claude/plans/objective-deploy-and-integrate-zany-bee.md Stream 6.
    # otel-collector fans traces out to BOTH GlitchTip (Sentry exporter,
    # ABSOLUTE-protected) AND Tempo (new otlp/tempo exporter). Picker
    # queries Tempo's TraceQL API for slow + error spans. Staggered at
    # :25/:55 (last in the chain) so no Postgres or Tempo contention.
    "auto-issues-tempo-pick": {
        "task": "auto_issues.pick_daily_tempo_findings",
        "schedule": crontab(hour="11-23", minute="25,55"),
        "options": {"queue": "default", "expires": 1500},
    },
    "auto-issues-internal-pick": {
        "task": "auto_issues.pick_daily_internal_issues",
        "schedule": crontab(hour=11, minute=20),
        "options": {"queue": "default", "expires": 600},
    },
    "auto-issues-slow-query-pick": {
        "task": "auto_issues.pick_daily_slow_queries",
        "schedule": crontab(hour=11, minute=25),
        "options": {"queue": "default", "expires": 600},
    },
    "auto-issues-close-stale": {
        "task": "auto_issues.close_stale_issues",
        "schedule": crontab(hour=11, minute=30),
        "options": {"queue": "default", "expires": 600},
    },
    # Gap-fillers wired 2026-05-09 — see docs/OBSERVABILITY-GAPS-EXTENSION.md.
    # All cron times inside the active-laptop window (11:00–23:00 UTC).
    "auto-issues-disk-pressure": {
        # Every hour on :40 within the active window — catches disk-fill
        # 5-23 hours BEFORE the wall.
        "task": "auto_issues.pick_disk_pressure",
        "schedule": crontab(hour="11-23", minute=40),
        "options": {"queue": "default", "expires": 600},
    },
    "auto-issues-slo-probes": {
        # Every 15 min within the active window — quick probes of all
        # in-stack endpoints. ~10 s per run × 4 runs/h × 13 h = 520 s/day.
        "task": "auto_issues.pick_slo_probes",
        "schedule": crontab(hour="11-23", minute="0,15,30,45"),
        "options": {"queue": "default", "expires": 300},
    },
    "auto-issues-missed-runs": {
        # Daily 11:45 — surfaces JobAlert rows that aren't yet
        # acknowledged into the same auto_issues feed.
        "task": "auto_issues.pick_missed_runs",
        "schedule": crontab(hour=11, minute=45),
        "options": {"queue": "default", "expires": 600},
    },
    "auto-issues-deploy-check": {
        # Weekly Tuesday 11:50 — Django `check --deploy` runs through
        # the security-warning catalog.
        "task": "auto_issues.pick_deploy_check_findings",
        "schedule": crontab(hour=11, minute=50, day_of_week=2),
        "options": {"queue": "default", "expires": 1800},
    },
    "auto-issues-output-quality": {
        # Daily 11:55 — domain-specific data-quality probes
        # (suggestion non-zero rate, page embedding coverage, etc).
        "task": "auto_issues.pick_output_quality",
        "schedule": crontab(hour=11, minute=55),
        "options": {"queue": "default", "expires": 1200},
    },
    # 90-day retention cleanup — runs weekly Sunday 12:00 UTC inside the
    # active-laptop window. Walks Pyroscope's /data, deletes blocks older
    # than 90 days; deletes audit_errorlog rows older than 90 days;
    # deletes resolved auto_issues older than 180 days. Weekly cadence
    # keeps the cleanup cost bounded (~1-2 min per run vs daily noise).
    "auto-issues-retention-cleanup": {
        "task": "auto_issues.run_retention_cleanup",
        "schedule": crontab(hour=12, minute=0, day_of_week=0),
        "options": {"queue": "default", "expires": 3600},
    },
    # pip-audit dependency-CVE scan: weekly Monday 11:35 UTC. Inside the
    # active-laptop window. Each CVE landed by `pick_pip_audit_findings`
    # becomes one AutoIssue row, deduped across weeks via stable
    # `(package, cve_id)` canonical fingerprint.
    "auto-issues-pip-audit-pick": {
        "task": "auto_issues.pick_weekly_pip_audit_findings",
        "schedule": crontab(hour=11, minute=35, day_of_week=1),
        "options": {"queue": "default", "expires": 1800},
    },
    # Crawler auto-prune: first Sunday 14:20 UTC.
    "crawler-auto-prune": {
        "task": "crawler.auto_prune",
        "schedule": crontab(hour=14, minute=20, day_of_week=0, day_of_month="1-7"),
        "options": {"queue": "pipeline"},
    },
    # Rejected-pair negative-memory prune: every Sunday 14:25 UTC.
    # Keeps RejectedPair table bounded by deleting rows past the 365-day
    # prune-after threshold (well beyond the 90-day suppression window).
    # See BUSINESS-LOGIC-CHECKLIST §6.3.
    "weekly-prune-rejected-pairs": {
        "task": "suggestions.prune_rejected_pairs",
        "schedule": crontab(hour=14, minute=25, day_of_week=0),
        "options": {"queue": "default"},
    },
    # ── Daytime / frequent tasks ─────────────────────────────────────
    # FR-019 — daily GSC spike detection: 11:00 UTC.
    # Moved from 08:00 → 11:00 on 2026-04-25 because the laptop is
    # asleep before ~10:00 (sleeps after 23:00, wakes ~10:00). 11:00
    # is the first slot inside the widened operator window where the
    # job is guaranteed to fire. See docs/PERFORMANCE.md and
    # apps/scheduled_updates/window.py for the window contract.
    "daily-gsc-spike-check": {
        "task": "pipeline.check_gsc_spikes",
        "schedule": crontab(hour=11, minute=0),
        "options": {"queue": "pipeline"},
    },
    # Automated system health check: Every 30 minutes.
    "periodic-system-health-check": {
        "task": "health.run_all_health_checks",
        "schedule": 1800.0,
        "options": {"queue": "pipeline"},
    },
    # FR-030 — FAISS-GPU index refresh: every 15 minutes.
    "refresh-faiss-index": {
        "task": "pipeline.refresh_faiss_index",
        "schedule": crontab(minute="*/15"),
        "options": {"queue": "pipeline"},
    },
    # FR-246 — NRT delta layer flush: every 60 seconds, but the task
    # itself short-circuits when the delta is below the flush
    # threshold (Bialecki 2012 SIGIR-OSIR §3 NRT pattern). Sub-minute
    # cadence is intentional — the delta is the freshness floor for
    # newly-embedded content between 15-minute base rebuilds.
    "nrt-delta-flush": {
        "task": "pipeline.nrt_delta_flush",
        "schedule": 60.0,
        "options": {"queue": "pipeline"},
    },
    # FR-245 — monthly Platt sigmoid recalibration. Guo et al. 2017 ICML
    # §5 — 30-day cadence is the recommended default for calibration on
    # deep models. The task short-circuits silently when the feedback
    # store has fewer than 1000 approved/rejected pairs (Niculescu-
    # Mizil & Caruana 2005 §4).
    "calibration-fit": {
        "task": "pipeline.calibration_fit",
        "schedule": crontab(minute=0, hour=3, day_of_month=1),
        "options": {"queue": "pipeline"},
    },
    # FR-053 — Passage-Level Relevance Scoring (Group E). Bounded
    # batch every 30 min so we never starve the GPU; the regenerator
    # itself is idempotent so unchanged content does zero work.
    "refresh-passage-embeddings": {
        "task": "pipeline.refresh_passage_embeddings",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "pipeline"},
    },
    # Group L #91 — daily local Postgres backup. 02:30 UTC sits inside
    # the operator's 11 AM – 11 PM laptop availability window across
    # most timezones; the task is bounded by a soft time limit, so a
    # missed-window run resumes on the next tick rather than starving
    # the rest of the queue. See ``apps.core.backups`` for the
    # disk-pressure pre-flight + retention policy (last 30 snapshots).
    "daily-database-backup": {
        "task": "core.create_database_snapshot",
        "schedule": crontab(minute=30, hour=2),
        "options": {"queue": "default"},
    },
    # Passkey hygiene — sweep expired WebAuthn challenges every 6 h.
    # Each PasskeyChallenge has a 5-min TTL; the finish handlers
    # opportunistically prune on each call, but a user who starts
    # registration and never finishes leaves a row behind. Bounded
    # task so it never holds a worker for long.
    "passkey-cleanup-expired-challenges": {
        "task": "core.passkey_cleanup_expired_challenges",
        "schedule": crontab(minute=15, hour="*/6"),
        "options": {"queue": "default", "expires": 3600},
    },
    # System heartbeat pulse: every 60 seconds.
    "pulse-heartbeat": {
        "task": "crawler.pulse_heartbeat",
        "schedule": 60.0,
        "options": {"queue": "default", "expires": 55},
    },
    # Watchdog check: every 5 minutes (checks for stuck jobs).
    "watchdog-check": {
        "task": "crawler.watchdog_check",
        "schedule": 300.0,
        "options": {"queue": "default", "expires": 290},
    },
    # Disk-pressure circuit breaker — every 60 s (DISK-PRESSURE-RULES.md).
    # Refreshes the cached state (GREEN/YELLOW/RED/CRITICAL) so callers
    # of `current_state()` and `require_free_disk()` see the latest free
    # disk without each one paying the `shutil.disk_usage()` cost.
    # First transition into YELLOW+ raises an OperatorAlert; repeats are
    # silenced by the dedup window inside the service module.
    "refresh-disk-pressure-state": {
        "task": "pipeline.refresh_disk_pressure_state",
        "schedule": 60.0,
        "options": {"queue": "default", "expires": 55},
    },
    # FR-247 SLO check — once per day at 04:00 UTC. Reads the in-memory
    # Stage-2 path counters and files an AutoIssue if the Python fallback
    # share has crept above `pipeline.cpp_path_alert_threshold` (default 5 %).
    # Catches silent C++ → Python regressions that the operator would
    # otherwise only see on the `/performance` dashboard. AutoIssue #14.
    "cpp-fallback-share-check": {
        "task": "pipeline.cpp_fallback_share_check",
        "schedule": crontab(minute=0, hour=4),
        "options": {"queue": "default", "expires": 3500},
    },
    # Plan item 12 + 14 — auto-revert performance mode every 5 minutes.
    # Reads system.performance_mode_expiry / _expires_at AppSettings and flips
    # HIGH to BALANCED when the "Until tonight ends" window closes.  Light
    # task: a few DB reads, at most one UPDATE, one alert.
    "auto-revert-performance-mode": {
        "task": "core.auto_revert_performance_mode",
        "schedule": 300.0,
        "options": {"queue": "default", "expires": 290},
    },
    # Plan item 19 — prune stale SyncJob checkpoint metadata at 14:25 UTC
    # daily.  Clears completed checkpoints >24h old and failed/paused >48h
    # old.  Light task: bulk UPDATE, no file I/O today (scratch-file pruning
    # ships once we have a canonical scratch directory).
    "prune-stale-checkpoints": {
        "task": "core.prune_stale_checkpoints",
        "schedule": crontab(hour=14, minute=25),
        "options": {"queue": "default"},
    },
    # Plan item 20 — prune superseded embedding archives older than 7 days
    # that have a verified replacement.  Unverified rows stay so operators
    # retain a rollback path if a bad embedding sneaks through.  Runs at
    # 14:50 UTC daily to stay clear of the 14:00-14:45 alert check band.
    "prune-superseded-embeddings": {
        "task": "core.prune_superseded_embeddings",
        "schedule": crontab(hour=14, minute=50),
        "options": {"queue": "default"},
    },
    # Plan item 30 — laptop-sleep-safe resume sweeper every 5 minutes.
    # Conservative: only undoes pauses that the wake watcher itself set, never
    # overrides an explicit user master-pause.
    "resume-after-wake": {
        "task": "core.resume_after_wake",
        "schedule": 300.0,
        "options": {"queue": "default", "expires": 290},
    },
    # Phase 2.18 — refresh dashboard materialised views every 5 minutes.
    # The matview pre-computes the suggestion-status histogram so the
    # Dashboard view reads it in microseconds instead of running a
    # full-table aggregate on every refresh. CONCURRENTLY refresh keeps
    # readers unblocked. 5-minute window keeps the data fresh enough for
    # operator decisions without the per-request query cost.
    "refresh-dashboard-matviews": {
        "task": "core.refresh_dashboard_matviews",
        "schedule": 300.0,
        "options": {"queue": "default", "expires": 290},
    },
    # ── Stage 9 alert rules: 14:30–14:45 UTC ────────────────────
    "check-silent-failure": {
        "task": "notifications.check_silent_failure",
        "schedule": crontab(hour=14, minute=30),
        "options": {"queue": "default"},
    },
    "check-zero-suggestion-run": {
        "task": "notifications.check_zero_suggestion_run",
        "schedule": crontab(hour=14, minute=35),
        "options": {"queue": "default"},
    },
    "check-post-link-regression": {
        "task": "notifications.check_post_link_regression",
        "schedule": crontab(hour=14, minute=40),
        "options": {"queue": "default"},
    },
    "check-autotune-status": {
        "task": "notifications.check_autotune_status",
        "schedule": crontab(hour=14, minute=45),
        "options": {"queue": "default"},
    },
    # Phase C — Weekly OPQ Codebook training: Sunday 14:55 UTC
    "weekly-train-opq-codebook": {
        "task": "passage_relevance.train_opq_codebook",
        "schedule": crontab(hour=14, minute=55, day_of_week=0),
        "options": {"queue": "pipeline"},
    },
    # Phase 4.14 — C++ Fallback Warning watcher.
    # Every 5 minutes: detect cpp↔python transitions, emit Operations
    # Feed events on transitions, re-emit "still down" reminders every
    # 1 h while a fallback persists. Cheap (just imports + state checks);
    # storage stays bounded via 1 AppSetting row per extension.
    "cpp-fallback-check": {
        "task": "core.cpp_fallback_check",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "default", "expires": 290},
    },
    # Phase 4.9 — Compression Audit (weekly read-only scan).
    # Sundays at 03:00 UTC: walk ~10 candidate tables, sample 1000
    # rows each, measure zlib compression ratio, persist a top-10
    # "would benefit from compression" report. Storage: 2 AppSetting
    # rows total (report + run-at timestamp); NO new tables.
    "weekly-compression-audit": {
        "task": "core.compression_audit",
        "schedule": crontab(day_of_week=0, hour=3, minute=0),
        "options": {"queue": "default"},
    },
    # Phase 4.11 — Performance Certification recompute.
    # Daily at 11:00 UTC (was 04:00 — moved 2026-05-09 to the active-laptop
    # window). Aggregates the latest completed BenchmarkRun into a
    # pass/fail verdict for the dashboard. Cheap (~1-2 s); does NOT
    # trigger a fresh benchmark run (separate manual operator action).
    "daily-performance-cert": {
        "task": "core.performance_cert_recompute",
        "schedule": crontab(hour=11, minute=0),
        "options": {"queue": "default"},
    },
    # Sentient-schedules — every 10 minutes, the schedule_tracker scans for
    # registered schedules whose expected slot has no row in the table (or
    # has a stale `pending` row) and fires the registered callable to catch
    # up. Idempotent via the (task_name, scheduled_for) unique constraint.
    # Also runs once on Django startup (see apps.core.apps.CoreConfig.ready)
    # so a laptop that's been off for hours catches up the moment it boots.
    "schedule-tracker-recovery-tick": {
        "task": "core.schedule_tracker_recovery_tick",
        "schedule": 600.0,
        "options": {"queue": "default", "expires": 540},
    },
    # Sentient-schedules — monthly Top-50 link suggestions on the 1st at 09:00 UTC.
    # The actual work runs via the management command `run_monthly_top_50`
    # which auto-detects Claude Code (Strategy A) and falls back to a pure
    # Python picker (Strategy B) when the AI isn't available.
    "monthly-top-50-suggestions": {
        "task": "pipeline.run_monthly_top_50_celery",
        "schedule": crontab(minute=0, hour=9, day_of_month=1),
        "options": {"queue": "pipeline"},
    },
}
