"""
Celery Beat schedule definitions.

Extracted from base.py to keep file length under the 500-line lint limit.
Imported by base.py via: from .celery_schedules import CELERY_BEAT_SCHEDULE
"""

from celery.schedules import crontab

CELERY_BEAT_SCHEDULE = {
    # ── FR-225 — Meta Rotation Tournament: 03:00 UTC daily (off-peak) ──
    # Runs after midnight when the system is idle. Sequential evaluation,
    # no concurrent shadow runs. Peak RAM <= 512 MB.
    "meta-rotation-tournament": {
        "task": "suggestions.meta_rotation_tournament",
        "schedule": crontab(hour=3, minute=0),
        "options": {"queue": "pipeline"},
    },
    # ── Heavy tasks: 21:00–22:00 UTC evening window ─────────────────
    # See docs/PERFORMANCE.md §5 for rationale (avoid Chrome/dev contention).
    "nightly-xenforo-sync": {
        "task": "pipeline.import_content",
        "schedule": crontab(hour=21, minute=0),
        "kwargs": {"source": "api", "mode": "full"},
        "options": {"queue": "pipeline"},
    },
    # Part 6.5 — monthly baseline refresh: 1st of every month.
    # Forces a full re-embedding to ensure zero drift from live sites.
    # Separated from monthly-cs-weight-tune to avoid slot collision.
    "monthly-xenforo-full-sync": {
        "task": "pipeline.import_content",
        "schedule": crontab(hour=21, minute=30, day_of_month="1"),
        "kwargs": {"source": "api", "mode": "full", "force_reembed": True},
        "options": {"queue": "pipeline"},
    },
    "monthly-wordpress-full-sync": {
        "task": "pipeline.import_content",
        "schedule": crontab(hour=22, minute=0, day_of_month="1"),
        "kwargs": {"source": "wp", "mode": "full", "force_reembed": True},
        "options": {"queue": "pipeline"},
    },
    # ── Medium tasks: 21:30–22:15 UTC ───────────────────────────────
    # FR-018 — monthly auto-tuner: 21:45 on the first Sunday of every month.
    "monthly-cs-weight-tune": {
        "task": "pipeline.monthly_weight_tune",
        "schedule": crontab(hour=21, minute=45, day_of_week=0, day_of_month="1-7"),
        "options": {"queue": "pipeline"},
    },
    # FR-025 — weekly session co-occurrence rebuild: Monday 21:30 UTC.
    "weekly-session-cooccurrence": {
        "task": "cooccurrence.compute_session_cooccurrence",
        "schedule": crontab(hour=21, minute=30, day_of_week=1),
        "options": {"queue": "default"},
    },
    # ── Light tasks: 22:00–22:30 UTC ────────────────────────────────
    # FR-018 — weekly GSC rollback check: Sunday 22:00 UTC.
    "weekly-weight-rollback-check": {
        "task": "pipeline.check_weight_rollback",
        "schedule": crontab(hour=22, minute=0, day_of_week=0),
        "options": {"queue": "pipeline"},
    },
    # Part 7 — nightly data retention: 22:00 UTC daily.
    "nightly-data-retention": {
        "task": "pipeline.nightly_data_retention",
        "schedule": crontab(hour=22, minute=0),
        "options": {"queue": "pipeline"},
    },
    # Stuck job cleanup: 22:10 UTC daily.
    "cleanup-stuck-sync-jobs": {
        "task": "pipeline.cleanup_stuck_sync_jobs",
        "schedule": crontab(hour=22, minute=10),
        "options": {"queue": "pipeline"},
    },
    # Part 9 — 12-week self-pruning: Sunday 22:15 UTC.
    "12-week-prune-stale-data": {
        "task": "pipeline.prune_stale_data",
        "schedule": crontab(hour=22, minute=15, day_of_week=0),
        "options": {"queue": "pipeline", "expires": 3600},
    },
    # Gap 3 — weekly reviewer scorecard computation: Monday 22:00 UTC.
    "weekly-reviewer-scorecard": {
        "task": "audit.compute_weekly_reviewer_scorecard",
        "schedule": crontab(hour=22, minute=0, day_of_week=1),
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
    # OPT-84 — nightly performance benchmarks: 22:15 UTC daily.
    "nightly-benchmarks": {
        "task": "apps.benchmarks.tasks.run_all_benchmarks",
        "schedule": crontab(hour=22, minute=15),
        "kwargs": {"trigger": "scheduled"},
        "options": {"queue": "default"},
    },
    # Crawler auto-prune: first Sunday 22:20 UTC.
    "crawler-auto-prune": {
        "task": "crawler.auto_prune",
        "schedule": crontab(hour=22, minute=20, day_of_week=0, day_of_month="1-7"),
        "options": {"queue": "pipeline"},
    },
    # Rejected-pair negative-memory prune: every Sunday 22:25 UTC.
    # Keeps RejectedPair table bounded by deleting rows past the 365-day
    # prune-after threshold (well beyond the 90-day suppression window).
    # See BUSINESS-LOGIC-CHECKLIST §6.3.
    "weekly-prune-rejected-pairs": {
        "task": "suggestions.prune_rejected_pairs",
        "schedule": crontab(hour=22, minute=25, day_of_week=0),
        "options": {"queue": "default"},
    },
    # ── Daytime / frequent tasks (unchanged) ────────────────────────
    # FR-019 — daily GSC spike detection: 08:00 UTC.
    "daily-gsc-spike-check": {
        "task": "pipeline.check_gsc_spikes",
        "schedule": crontab(hour=8, minute=0),
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
    # Plan item 19 — prune stale SyncJob checkpoint metadata at 22:25 UTC
    # nightly.  Clears completed checkpoints >24h old and failed/paused >48h
    # old.  Light task: bulk UPDATE, no file I/O today (scratch-file pruning
    # ships once we have a canonical scratch directory).
    "prune-stale-checkpoints": {
        "task": "core.prune_stale_checkpoints",
        "schedule": crontab(hour=22, minute=25),
        "options": {"queue": "default"},
    },
    # Plan item 20 — prune superseded embedding archives older than 7 days
    # that have a verified replacement.  Unverified rows stay so operators
    # retain a rollback path if a bad embedding sneaks through.  Runs at
    # 22:50 UTC nightly to stay clear of the 22:00-22:45 alert check band.
    "prune-superseded-embeddings": {
        "task": "core.prune_superseded_embeddings",
        "schedule": crontab(hour=22, minute=50),
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
    # ── Stage 9 alert rules: 22:30–22:45 UTC ────────────────────
    "check-silent-failure": {
        "task": "notifications.check_silent_failure",
        "schedule": crontab(hour=22, minute=30),
        "options": {"queue": "default"},
    },
    "check-zero-suggestion-run": {
        "task": "notifications.check_zero_suggestion_run",
        "schedule": crontab(hour=22, minute=35),
        "options": {"queue": "default"},
    },
    "check-post-link-regression": {
        "task": "notifications.check_post_link_regression",
        "schedule": crontab(hour=22, minute=40),
        "options": {"queue": "default"},
    },
    "check-autotune-status": {
        "task": "notifications.check_autotune_status",
        "schedule": crontab(hour=22, minute=45),
        "options": {"queue": "default"},
    },
}
