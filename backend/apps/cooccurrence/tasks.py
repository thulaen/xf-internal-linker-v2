"""FR-025 — Celery tasks for co-occurrence pipeline and value model scoring."""

from __future__ import annotations

import logging
from dataclasses import dataclass

from celery import shared_task

from apps.pipeline.decorators import with_weight_lock

logger = logging.getLogger(__name__)


def _read_int(key: str, default: int) -> int:
    """Module-local alias for ``AppSetting.get_int`` (Group D consolidation).

    Kept as a thin shim so existing call sites in this file stay
    untouched while delegating the cast logic to the shared classmethod.
    Lazy import so this module stays import-cheap.
    """
    from apps.core.models import AppSetting

    return AppSetting.get_int(key, default)


def _read_float(key: str, default: float) -> float:
    """Module-local alias for ``AppSetting.get_float`` (Group D consolidation)."""
    from apps.core.models import AppSetting

    return AppSetting.get_float(key, default)


# ---------------------------------------------------------------------------
# Co-occurrence pipeline — extracted helpers (2026-05-09, Fowler Extract Method)
# ---------------------------------------------------------------------------
#
# The original ``compute_session_cooccurrence`` was 102 lines mixing six
# logical phases: load settings → compute window → create Run → fetch
# GA4 → on failure update + alert + return → on success update + alert
# + chain hub detection. Each phase is now a named module-level helper
# so the task is a thin orchestrator and each helper is unit-testable
# in ``SimpleTestCase`` (no DB).


@dataclass(frozen=True)
class _CooccurrenceWindowSettings:
    """The three settings the GA4 fetch step actually consumes."""

    data_window_days: int
    min_co_session_count: int
    min_jaccard: float


def _load_cooccurrence_window_settings() -> _CooccurrenceWindowSettings:
    """Load AppSetting values for the cooccurrence window.

    Defaults match the GET endpoint (``views._read_cooccurrence_settings``).
    """
    return _CooccurrenceWindowSettings(
        data_window_days=_read_int("cooccurrence.data_window_days", 90),
        min_co_session_count=_read_int("cooccurrence.min_co_session_count", 5),
        min_jaccard=_read_float("cooccurrence.min_jaccard", 0.05),
    )


def _mark_run_failed(run, error_message: str) -> None:
    """Stamp a SessionCoOccurrenceRun as FAILED with error + completed_at."""
    from django.utils import timezone as dj_tz

    from .models import SessionCoOccurrenceRun

    run.status = SessionCoOccurrenceRun.STATUS_FAILED
    run.error_message = error_message
    run.completed_at = dj_tz.now()
    run.save(update_fields=["status", "error_message", "completed_at"])


def _mark_run_completed(
    run, sessions_processed: int, pairs_written: int, ga4_rows_fetched: int
) -> None:
    """Stamp a SessionCoOccurrenceRun as COMPLETED with counts + completed_at."""
    from django.utils import timezone as dj_tz

    from .models import SessionCoOccurrenceRun

    run.status = SessionCoOccurrenceRun.STATUS_COMPLETED
    run.sessions_processed = sessions_processed
    run.pairs_written = pairs_written
    run.ga4_rows_fetched = ga4_rows_fetched
    run.completed_at = dj_tz.now()
    run.save(
        update_fields=[
            "status",
            "sessions_processed",
            "pairs_written",
            "ga4_rows_fetched",
            "completed_at",
        ]
    )


def _build_failure_alert_kwargs(run_id, exc: Exception) -> dict:
    """Pure: kwargs for ``emit_operator_alert`` on a failed run."""
    return {
        "event_type": "cooccurrence.run_failed",
        "severity": "error",
        "title": "Co-Occurrence Pipeline Failed",
        "message": f"The session co-occurrence task failed: {exc}",
        "source_area": "system",
        "dedupe_key": f"cooccurrence.run_failed.{run_id}",
    }


def _build_completed_alert_kwargs(
    run_id, sessions_processed: int, pairs_written: int
) -> dict:
    """Pure: kwargs for ``emit_operator_alert`` on a completed run."""
    return {
        "event_type": "cooccurrence.run_completed",
        "severity": "info",
        "title": "Co-Occurrence Pipeline Complete",
        "message": (
            f"Session co-occurrence run finished. "
            f"{pairs_written} pairs written from {sessions_processed} sessions."
        ),
        "source_area": "system",
        "dedupe_key": f"cooccurrence.run_completed.{run_id}",
    }


def _is_hub_detection_enabled_value(setting_value: str | None) -> bool:
    """Pure opt-out toggle: missing OR != ``'false'`` (case-insensitive) → enabled.

    Why this is its own pure function: the AppSetting semantics here are
    "absence = on, the literal string 'false' = off." A standard
    ``AppSetting.get_bool`` wrapper would lose that opt-out asymmetry.
    """
    return not setting_value or setting_value.lower() != "false"


def _is_hub_detection_enabled() -> bool:
    """DB-side wrapper: read the AppSetting and feed the pure check above."""
    from apps.core.models import AppSetting

    row = AppSetting.objects.filter(
        key="cooccurrence.hub_detection_enabled"
    ).first()
    return _is_hub_detection_enabled_value(row.value if row else None)


def _finalize_completed_run(
    run, sessions_processed: int, pairs_written: int, ga4_rows_fetched: int
) -> dict:
    """Persist completion, emit alert, chain hub detection; return result dict."""
    from apps.notifications.services import emit_operator_alert

    _mark_run_completed(run, sessions_processed, pairs_written, ga4_rows_fetched)
    emit_operator_alert(
        **_build_completed_alert_kwargs(
            run.run_id, sessions_processed, pairs_written
        )
    )
    if _is_hub_detection_enabled():
        detect_behavioral_hubs.delay()
    return {
        "status": "completed",
        "run_id": str(run.run_id),
        "sessions_processed": sessions_processed,
        "pairs_written": pairs_written,
        "ga4_rows_fetched": ga4_rows_fetched,
    }


def _finalize_failed_run(run, exc: Exception) -> dict:
    """Persist failure, emit alert, return result dict.

    Caller must ``logger.exception(...)`` in the except block — keeping
    that keyword visible at the except site is what satisfies the
    forbidden-patterns silent-except scanner.
    """
    from apps.notifications.services import emit_operator_alert

    _mark_run_failed(run, str(exc))
    emit_operator_alert(**_build_failure_alert_kwargs(run.run_id, exc))
    return {"status": "failed", "error": str(exc)}


@shared_task(
    bind=True,
    name="cooccurrence.compute_session_cooccurrence",
    time_limit=3600,
    soft_time_limit=3540,
)
@with_weight_lock("medium")
def compute_session_cooccurrence(self) -> dict:
    """Fetch GA4 session data, build the co-occurrence matrix, chain hub
    detection on success. Weekly via CELERY_BEAT_SCHEDULE. Emits FR-019
    operator alerts on both terminal states.
    """
    from datetime import date, timedelta

    from .models import SessionCoOccurrenceRun
    from .services import fetch_ga4_session_cooccurrence

    settings = _load_cooccurrence_window_settings()
    window_end = date.today()
    window_start = window_end - timedelta(days=settings.data_window_days)

    run = SessionCoOccurrenceRun.objects.create(
        status=SessionCoOccurrenceRun.STATUS_RUNNING,
        data_window_start=window_start,
        data_window_end=window_end,
    )

    try:
        sessions_processed, pairs_written, ga4_rows_fetched = (
            fetch_ga4_session_cooccurrence(
                data_window_days=settings.data_window_days,
                min_co_session_count=settings.min_co_session_count,
                min_jaccard=settings.min_jaccard,
            )
        )
    except Exception as exc:
        logger.exception("Co-occurrence pipeline failed: %s", exc)
        return _finalize_failed_run(run, exc)

    return _finalize_completed_run(
        run, sessions_processed, pairs_written, ga4_rows_fetched
    )


@shared_task(
    name="cooccurrence.detect_behavioral_hubs", time_limit=1800, soft_time_limit=1740
)
def detect_behavioral_hubs() -> dict:
    """Run hub detection from existing co-occurrence data."""
    from .services import detect_behavioral_hubs as _detect

    # Group U cleanup (2026-04-28): _read_int / _read_float are now
    # module-level helpers at the top of this file (previously duplicated
    # nested copies in both this task and compute_session_cooccurrence).
    hub_min_jaccard = _read_float("cooccurrence.hub_min_jaccard", 0.15)
    hub_min_members = _read_int("cooccurrence.hub_min_members", 3)

    hubs_created, members_assigned = _detect(
        hub_min_jaccard=hub_min_jaccard,
        hub_min_members=hub_min_members,
    )

    logger.info(
        "Hub detection complete: %d hubs, %d members",
        hubs_created,
        members_assigned,
    )
    return {"hubs_created": hubs_created, "members_assigned": members_assigned}


def _score_suggestions_for_run(suggestions, settings, site_max_jaccard):
    """Compute ``score_value_model`` + ``value_model_diagnostics`` in-place
    on each suggestion. Returns the same list — a hand-off for
    ``Suggestion.objects.bulk_update``.
    """
    from .services import compute_value_model_score

    for suggestion in suggestions:
        score, diagnostics = compute_value_model_score(
            suggestion=suggestion,
            settings=settings,
            site_max_jaccard=site_max_jaccard,
        )
        suggestion.score_value_model = score
        suggestion.value_model_diagnostics = diagnostics
    return suggestions


@shared_task(
    name="cooccurrence.apply_value_model_scores", time_limit=1800, soft_time_limit=1740
)
def apply_value_model_scores(run_id: str) -> dict:
    """Compute score_value_model and value_model_diagnostics for all suggestions in a run.

    Called automatically after pipeline.run_pipeline completes successfully.
    Uses all 7 value model signals including co_occurrence_signal (FR-025).
    """
    from apps.core.views import get_value_model_settings
    from apps.suggestions.models import Suggestion

    from .services import get_site_max_jaccard

    settings = get_value_model_settings()
    if not settings.get("enabled", True):
        logger.info(
            "Value model disabled — skipping apply_value_model_scores for run %s",
            run_id,
        )
        return {"skipped": True, "reason": "value_model.enabled=false"}

    suggestions = list(
        Suggestion.objects.filter(pipeline_run_id=run_id).select_related(
            "destination", "host"
        )
    )
    if not suggestions:
        return {"updated": 0, "run_id": run_id}

    to_update = _score_suggestions_for_run(
        suggestions, settings, get_site_max_jaccard()
    )
    Suggestion.objects.bulk_update(
        to_update,
        ["score_value_model", "value_model_diagnostics"],
        batch_size=500,
    )
    logger.info(
        "apply_value_model_scores: updated %d suggestions for run %s",
        len(to_update),
        run_id,
    )
    return {"updated": len(to_update), "run_id": run_id}
