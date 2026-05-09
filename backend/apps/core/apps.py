"""Core app — shared models, base classes, and utilities used across all apps."""

import logging

from django.apps import AppConfig
from django.db.models.signals import post_migrate

logger = logging.getLogger(__name__)


def _record_safe_mode_history(prior_value: str) -> None:
    """Best-effort audit trail for the safe-mode-boot flag consumption.

    Lazy-imported `write_history` so `core` doesn't grow a hard dependency
    on `suggestions` at boot time; failure here must not crash startup.
    """
    try:
        from apps.suggestions.weight_preset_service import write_history

        write_history(
            source="system_boot_safe_mode",
            previous_weights={"system.performance_mode": str(prior_value)},
            new_weights={"system.performance_mode": "safe"},
            reason=(
                "Safe-mode-boot flag consumed at startup — performance "
                "mode forced to 'safe' by user-armed panic recovery."
            ),
        )
    except Exception:
        logger.debug(
            "Could not write history for safe-mode-boot flag consumption",
            exc_info=True,
        )


def _consume_safe_mode_boot_flag(sender, **kwargs):
    """If a prior session armed the safe-mode-boot flag, force Performance Mode
    to 'safe' now and clear the flag. Runs once per process after migrations.

    This is the "panic recovery" path: a noob user who got stuck on High
    Performance can arm the flag, restart the backend, and come back to Safe
    mode without touching the database directly.
    """
    try:
        from apps.core.models import AppSetting
    except Exception:  # noqa: BLE001  # pragma: no cover — defensive: app registry may not be ready yet at startup; safest action is just to skip the panic-recovery flag for this boot.
        return

    try:
        from django.db import transaction

        flag = (
            AppSetting.objects.filter(key="system.boot_safe_once")
            .values_list("value", flat=True)
            .first()
        )
        if not (flag and str(flag).lower() == "true"):
            return

        # Capture prior value so the audit trail records what changed.
        prior_value = (
            AppSetting.objects.filter(key="system.performance_mode")
            .values_list("value", flat=True)
            .first()
        ) or "default"

        with transaction.atomic():
            AppSetting.objects.update_or_create(
                key="system.performance_mode",
                defaults={
                    "value": "safe",
                    "value_type": "str",
                    "category": "performance",
                },
            )
            AppSetting.objects.filter(key="system.boot_safe_once").delete()

        _record_safe_mode_history(prior_value)
        logger.warning(
            "Safe-mode-boot flag consumed: performance mode forced to 'safe' (was '%s').",
            prior_value,
        )
    except Exception:
        logger.exception("Could not consume safe-mode-boot flag")


def _run_startup_smoke_tests(sender, **kwargs):
    # Skip during test runs: each test-DB boot would otherwise emit
    # ErrorLog rows for every artefact-table policy gap and chain into
    # OperatorAlert via post_save, polluting test isolation. Tests that
    # exercise the smoke logic call `run_startup_smoke_tests()` directly.
    import sys

    if any(arg == "test" for arg in sys.argv[1:3]):
        return
    using = kwargs.get("using", "default")
    try:
        from django.db import connections

        db_name = connections[using].settings_dict.get("NAME") or ""
        if isinstance(db_name, str) and db_name.startswith("test_"):
            return
    except Exception:
        logger.debug("Smoke-test test-DB detection failed", exc_info=True)

    try:
        from apps.core.services.self_test_smoke import run_startup_smoke_tests

        run_startup_smoke_tests()
    except Exception:
        logger.exception("Could not run startup smoke tests")


class CoreConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.core"
    verbose_name = "Core"

    def ready(self):
        # Run after migrations to avoid touching the table before it exists.
        post_migrate.connect(_consume_safe_mode_boot_flag, sender=self)
        post_migrate.connect(_run_startup_smoke_tests, sender=self)
        post_migrate.connect(_run_schedule_recovery, sender=self)

        # Phase R1.3 — realtime broadcast signals for AppSetting changes.
        # Idempotent via dispatch_uid on each receiver.
        from . import signals  # noqa: F401

        # Startup safety check — warn loudly if auth_user is empty AND
        # backups/ already has snapshots (a Docker-rebuild data-loss
        # signature). Read-only, no writes.
        from . import checks_users  # noqa: F401

        # Sentient-schedules — explicit import so the @shared_task decorator
        # registers the recovery tick with Celery. Mirrors the existing
        # pattern for tasks_passkey_cleanup etc.
        from . import tasks_schedule_recovery  # noqa: F401

        # Register the operationally-important infrequent celery-beat
        # schedules with the sentient-schedule tracker so they get the
        # missed-run recovery treatment too. Best-effort: registration
        # failure must not crash startup.
        try:
            _register_existing_celery_schedules()
        except Exception:
            logger.exception(
                "core.ready: failed to register existing celery schedules with tracker"
            )


# Lookback windows by cadence. Frequent ticks aren't registered at all
# (the next firing happens soon enough naturally); for the rest we size
# the window so a recovered batch never replays an unreasonable backlog.
_DAILY_LOOKBACK_HOURS = 72  # 3-day catch-up window
_WEEKLY_LOOKBACK_HOURS = 24 * 14  # 2 weeks
_MONTHLY_LOOKBACK_HOURS = 24 * 35  # ~5 weeks

# (tracker_key, celery_task, kwargs, cron, description)
# tracker_key uses the BEAT entry name (always unique). The same celery
# task may appear with different kwargs across entries (e.g.
# pipeline.import_content scheduled both daily-full and monthly-force-
# reembed); using the beat-entry name keeps registry keys collision-free.
_DAILY_SCHEDULES: tuple[tuple[str, str, dict, str, str], ...] = (
    (
        "daily-database-backup",
        "core.create_database_snapshot",
        {},
        "30 2 * * *",
        "Daily local Postgres snapshot at 02:30 UTC.",
    ),
    (
        "nightly-xenforo-sync",
        "pipeline.import_content",
        {"source": "api", "mode": "full"},
        "0 13 * * *",
        "Nightly XenForo full-sync at 13:00 UTC.",
    ),
    (
        "cleanup-stuck-sync-jobs",
        "pipeline.cleanup_stuck_sync_jobs",
        {},
        "10 14 * * *",
        "Daily cleanup of stuck SyncJob rows at 14:10 UTC.",
    ),
    (
        "daily-gsc-spike-check",
        "pipeline.check_gsc_spikes",
        {},
        "0 11 * * *",
        "FR-019 daily Google Search Console spike check at 11:00 UTC.",
    ),
    (
        "nightly-benchmarks",
        "apps.benchmarks.tasks.run_all_benchmarks",
        {"trigger": "scheduled"},
        "15 14 * * *",
        "Daily performance benchmarks at 14:15 UTC.",
    ),
    (
        "prune-stale-checkpoints",
        "core.prune_stale_checkpoints",
        {},
        "25 14 * * *",
        "Daily cleanup of stale SyncJob checkpoints at 14:25 UTC.",
    ),
    (
        "prune-superseded-embeddings",
        "core.prune_superseded_embeddings",
        {},
        "50 14 * * *",
        "Daily prune of superseded embedding archives at 14:50 UTC.",
    ),
    (
        "daily-performance-cert",
        "core.performance_cert_recompute",
        {},
        "0 4 * * *",
        "Daily Performance Certification recompute at 04:00 UTC.",
    ),
    (
        "check-silent-failure",
        "notifications.check_silent_failure",
        {},
        "30 14 * * *",
        "Daily silent-failure alert check at 14:30 UTC.",
    ),
    (
        "check-zero-suggestion-run",
        "notifications.check_zero_suggestion_run",
        {},
        "35 14 * * *",
        "Daily zero-suggestion-run alert check at 14:35 UTC.",
    ),
    (
        "check-post-link-regression",
        "notifications.check_post_link_regression",
        {},
        "40 14 * * *",
        "Daily post-link-regression alert check at 14:40 UTC.",
    ),
    (
        "check-autotune-status",
        "notifications.check_autotune_status",
        {},
        "45 14 * * *",
        "Daily autotune-status alert check at 14:45 UTC.",
    ),
    (
        "scheduled-updates-prune-resolved-alerts",
        "scheduled_updates.prune_resolved_alerts",
        {},
        "45 22 * * *",
        "Late-window prune of resolved JobAlert rows at 22:45 UTC.",
    ),
)

_WEEKLY_SCHEDULES: tuple[tuple[str, str, dict, str, str], ...] = (
    (
        "weekly-session-cooccurrence",
        "cooccurrence.compute_session_cooccurrence",
        {},
        "30 13 * * 1",
        "FR-025 weekly session co-occurrence rebuild — Monday 13:30 UTC.",
    ),
    (
        "weekly-reviewer-scorecard",
        "audit.compute_weekly_reviewer_scorecard",
        {},
        "0 14 * * 1",
        "Weekly reviewer scorecard — Monday 14:00 UTC.",
    ),
    (
        "weekly-weight-rollback-check",
        "pipeline.check_weight_rollback",
        {},
        "0 14 * * 0",
        "FR-018 weekly GSC rollback check — Sunday 14:00 UTC.",
    ),
    (
        "12-week-prune-stale-data",
        "pipeline.prune_stale_data",
        {},
        "15 14 * * 0",
        "12-week self-pruning — Sunday 14:15 UTC.",
    ),
    (
        "weekly-prune-rejected-pairs",
        "suggestions.prune_rejected_pairs",
        {},
        "25 14 * * 0",
        "Weekly RejectedPair retention prune — Sunday 14:25 UTC.",
    ),
    (
        "weekly-train-opq-codebook",
        "passage_relevance.train_opq_codebook",
        {},
        "55 14 * * 0",
        "Weekly OPQ codebook training — Sunday 14:55 UTC.",
    ),
    (
        "weekly-compression-audit",
        "core.compression_audit",
        {},
        "0 3 * * 0",
        "Weekly compression audit — Sunday 03:00 UTC.",
    ),
    (
        "fortnightly-embedding-accuracy",
        "pipeline.embedding_accuracy_audit",
        {"fortnightly": True},
        "0 13 * * 4",
        "Fortnightly embedding accuracy audit — Thursday 13:00 UTC.",
    ),
)

_MONTHLY_SCHEDULES: tuple[tuple[str, str, dict, str, str], ...] = (
    (
        "monthly-embedding-bakeoff",
        "pipeline.embedding_provider_bakeoff",
        {},
        "30 14 1 * *",
        "Monthly embedding provider bake-off — 1st at 14:30 UTC.",
    ),
    (
        "monthly-xenforo-full-sync",
        "pipeline.import_content",
        {"source": "api", "mode": "full", "force_reembed": True},
        "30 13 1 * *",
        "Monthly XenForo full-sync (force re-embed) — 1st at 13:30 UTC.",
    ),
    (
        "monthly-wordpress-full-sync",
        "pipeline.import_content",
        {"source": "wp", "mode": "full", "force_reembed": True},
        "0 14 1 * *",
        "Monthly WordPress full-sync (force re-embed) — 1st at 14:00 UTC.",
    ),
    (
        "monthly-python-weight-tune",
        "pipeline.monthly_weight_tune",
        {},
        "45 13 1-7 * 0",
        "FR-018 monthly auto-tuner — 1st Sunday at 13:45 UTC.",
    ),
    (
        "monthly-python-meta-tune",
        "pipeline.monthly_meta_tune",
        {},
        "15 14 1-7 * 0",
        "FR-018b monthly meta-algorithm auto-tuner — 1st Sunday at 14:15 UTC.",
    ),
    (
        "calibration-fit",
        "pipeline.calibration_fit",
        {},
        "0 3 1 * *",
        "FR-245 monthly Platt calibration fit — 1st at 03:00 UTC.",
    ),
)


def _register_existing_celery_schedules() -> None:
    """Register the operationally-important infrequent celery-beat schedules.

    Walks the three tuples above and hands each one to the sentient-schedule
    tracker. Each fire callable invokes ``celery_app.send_task`` with the
    matching task name + kwargs so a recovered run reproduces the same
    parameters as the normal Beat firing would.
    """
    from apps.core.services.schedule_tracker import register_schedule
    from config.celery import app as celery_app  # noqa: PLC0415

    def fire(celery_task: str, kwargs: dict):
        def _send(_slot):
            celery_app.send_task(celery_task, kwargs=kwargs or {})

        return _send

    for spec_list, lookback in (
        (_DAILY_SCHEDULES, _DAILY_LOOKBACK_HOURS),
        (_WEEKLY_SCHEDULES, _WEEKLY_LOOKBACK_HOURS),
        (_MONTHLY_SCHEDULES, _MONTHLY_LOOKBACK_HOURS),
    ):
        for tracker_key, celery_task, kwargs, cron, desc in spec_list:
            register_schedule(
                tracker_key,
                cron,
                fire(celery_task, kwargs),
                max_lookback_hours=lookback,
                description=desc,
            )


def _run_schedule_recovery(sender, **kwargs):
    """Fire any missed scheduled runs once the DB is ready.

    Sentient-schedules recovery hook — runs after migrations, every time
    Django boots. If the laptop was off when a registered schedule was
    supposed to fire, the tracker notices the missing row and dispatches
    the registered callable now (with a 5-30s jitter so 10 missed schedules
    don't all fire at the exact same second).
    """
    import sys

    if any(arg == "test" for arg in sys.argv[1:3]):
        return
    using = kwargs.get("using", "default")
    try:
        from django.db import connections

        db_name = connections[using].settings_dict.get("NAME") or ""
        if isinstance(db_name, str) and db_name.startswith("test_"):
            return
    except Exception:
        logger.debug("Schedule-recovery test-DB detection failed", exc_info=True)

    try:
        from apps.core.services.schedule_tracker import recover_missed_runs

        fired = recover_missed_runs()
        if fired:
            logger.info(
                "schedule_tracker: dispatched %d missed run(s) on startup", fired
            )
    except Exception:
        logger.exception("schedule_tracker: startup recovery sweep failed")
