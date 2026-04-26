"""Startup catch-up registry.

Maps Celery Beat task names to their catch-up parameters.  When the worker
starts, ``catchup.run_startup_catchup()`` reads this registry, checks each
task's ``PeriodicTask.last_run_at``, and dispatches overdue tasks in priority
order with a 30-second stagger between Heavy tasks.

See docs/PERFORMANCE.md §4 for weight-class definitions and §5 for schedule
contract details.

Adding a new task:
    1. Add its Beat entry to ``celery_schedules.py``.
    2. Add a row here.
    3. Add the weight-class row in ``docs/PERFORMANCE.md`` §4.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CatchupEntry:
    """Parameters for a single catch-up-eligible Beat task."""

    # Maximum hours since last run before the task is considered overdue.
    threshold_hours: float
    # Lower number = dispatched first.
    priority: int
    # Celery queue to dispatch into.
    queue: str
    # Weight class: "heavy", "medium", or "light".
    weight_class: str


# ── Registry ────────────────────────────────────────────────────────
# Keys are Beat task *names* (the string keys in CELERY_BEAT_SCHEDULE).
# Only tasks that make sense to catch up are listed here.
#
# NOT eligible (too frequent or stateless):
#   periodic-system-health-check, refresh-faiss-index, pulse-heartbeat,
#   watchdog-check, daily-gsc-spike-check.

CATCHUP_REGISTRY: dict[str, CatchupEntry] = {
    # ── Heavy ───────────────────────────────────────────────────────
    "nightly-xenforo-sync": CatchupEntry(
        threshold_hours=26,
        priority=10,
        queue="pipeline",
        weight_class="heavy",
    ),
    "monthly-xenforo-full-sync": CatchupEntry(
        threshold_hours=35 * 24,  # 35 days
        priority=20,
        queue="pipeline",
        weight_class="heavy",
    ),
    "monthly-wordpress-full-sync": CatchupEntry(
        threshold_hours=35 * 24,
        priority=25,
        queue="pipeline",
        weight_class="heavy",
    ),
    # ── Medium ──────────────────────────────────────────────────────
    "weekly-session-cooccurrence": CatchupEntry(
        threshold_hours=8 * 24,  # 8 days
        priority=70,
        queue="pipeline",
        weight_class="medium",
    ),
    "monthly-python-weight-tune": CatchupEntry(
        threshold_hours=35 * 24,
        priority=90,
        queue="pipeline",
        weight_class="medium",
    ),
    # ── Light ───────────────────────────────────────────────────────
    "nightly-data-retention": CatchupEntry(
        threshold_hours=26,
        priority=50,
        queue="default",
        weight_class="light",
    ),
    "cleanup-stuck-sync-jobs": CatchupEntry(
        threshold_hours=26,
        priority=55,
        queue="default",
        weight_class="light",
    ),
    "nightly-benchmarks": CatchupEntry(
        threshold_hours=26,
        priority=60,
        queue="default",
        weight_class="light",
    ),
    "weekly-reviewer-scorecard": CatchupEntry(
        threshold_hours=8 * 24,
        priority=75,
        queue="default",
        weight_class="light",
    ),
    "weekly-weight-rollback-check": CatchupEntry(
        threshold_hours=8 * 24,
        priority=80,
        queue="default",
        weight_class="light",
    ),
    "12-week-prune-stale-data": CatchupEntry(
        threshold_hours=13 * 7 * 24,  # 13 weeks
        priority=95,
        queue="default",
        weight_class="light",
    ),
    "crawler-auto-prune": CatchupEntry(
        threshold_hours=5 * 7 * 24,  # 5 weeks
        priority=96,
        queue="default",
        weight_class="light",
    ),
    # ── Stage 9 alert rules (Light) ─────────────────────────────────
    "check-silent-failure": CatchupEntry(
        threshold_hours=26,
        priority=40,
        queue="default",
        weight_class="light",
    ),
    "check-zero-suggestion-run": CatchupEntry(
        threshold_hours=26,
        priority=42,
        queue="default",
        weight_class="light",
    ),
    "check-post-link-regression": CatchupEntry(
        threshold_hours=26,
        priority=44,
        queue="default",
        weight_class="light",
    ),
    "check-autotune-status": CatchupEntry(
        threshold_hours=26,
        priority=46,
        queue="default",
        weight_class="light",
    ),
    # ── Embedding health & quality (plan Parts 3 + 4) ─────────────
    "fortnightly-embedding-accuracy": CatchupEntry(
        threshold_hours=14 * 24,  # 336 h
        priority=35,
        queue="pipeline",
        weight_class="medium",
    ),
    "monthly-embedding-bakeoff": CatchupEntry(
        threshold_hours=35 * 24,
        priority=38,
        queue="pipeline",
        weight_class="medium",
    ),
}

_HEAVY_STAGGER_SECONDS = 30
"""Seconds to wait between dispatching consecutive Heavy tasks."""
