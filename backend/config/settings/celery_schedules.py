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
    # Phase GT Step 7 — GlitchTip issue sync every 30 minutes.
    # Off-minute scheduling so multiple projects don't stampede the
    # GlitchTip API at :00/:30. Expires at 29 min so a stuck run can't
    # overlap the next one.
    "glitchtip-issue-sync": {
        "task": "audit.sync_glitchtip_issues",
        "schedule": 1800.0,
        "options": {"queue": "default", "expires": 1700},
    },
    # OPT-84 — daily performance benchmarks: 14:15 UTC.
    "nightly-benchmarks": {
        "task": "apps.benchmarks.tasks.run_all_benchmarks",
        "schedule": crontab(hour=14, minute=15),
        "kwargs": {"trigger": "scheduled"},
        "options": {"queue": "default"},
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
}
