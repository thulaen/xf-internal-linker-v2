"""FR-025 — Celery tasks for co-occurrence pipeline and value model scoring."""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="cooccurrence.compute_session_cooccurrence",
    time_limit=3600,
    soft_time_limit=3540,
)
def compute_session_cooccurrence() -> dict:
    """Fetch GA4 session data and build the co-occurrence matrix.

    Runs weekly (scheduled via CELERY_BEAT_SCHEDULE).
    On success, chains detect_behavioral_hubs.
    Emits FR-019 operator alerts on failure and completion.
    """
    from django.utils import timezone as dj_tz
    from apps.core.models import AppSetting
    from apps.notifications.services import emit_operator_alert
    from .models import SessionCoOccurrenceRun
    from .services import fetch_ga4_session_cooccurrence

    def _read_int(key: str, default: int) -> int:
        try:
            return int(AppSetting.objects.get(key=key).value)
        except (AppSetting.DoesNotExist, ValueError):
            return default

    def _read_float(key: str, default: float) -> float:
        try:
            return float(AppSetting.objects.get(key=key).value)
        except (AppSetting.DoesNotExist, ValueError):
            return default

    data_window_days = _read_int("cooccurrence.data_window_days", 90)
    min_co_session_count = _read_int("cooccurrence.min_co_session_count", 5)
    min_jaccard = _read_float("cooccurrence.min_jaccard", 0.05)

    from datetime import date, timedelta

    window_end = date.today()
    window_start = window_end - timedelta(days=data_window_days)

    run = SessionCoOccurrenceRun.objects.create(
        status=SessionCoOccurrenceRun.STATUS_RUNNING,
        data_window_start=window_start,
        data_window_end=window_end,
    )

    try:
        sessions_processed, pairs_written, ga4_rows_fetched = (
            fetch_ga4_session_cooccurrence(
                data_window_days=data_window_days,
                min_co_session_count=min_co_session_count,
                min_jaccard=min_jaccard,
            )
        )
    except Exception as exc:
        run.status = SessionCoOccurrenceRun.STATUS_FAILED
        run.error_message = str(exc)
        run.completed_at = dj_tz.now()
        run.save(update_fields=["status", "error_message", "completed_at"])
        logger.exception("Co-occurrence pipeline failed: %s", exc)
        emit_operator_alert(
            event_type="cooccurrence.run_failed",
            severity="error",
            title="Co-Occurrence Pipeline Failed",
            message=f"The session co-occurrence task failed: {exc}",
            source_area="system",
            dedupe_key=f"cooccurrence.run_failed.{run.run_id}",
        )
        return {"status": "failed", "error": str(exc)}

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

    emit_operator_alert(
        event_type="cooccurrence.run_completed",
        severity="info",
        title="Co-Occurrence Pipeline Complete",
        message=(
            f"Session co-occurrence run finished. "
            f"{pairs_written} pairs written from {sessions_processed} sessions."
        ),
        source_area="system",
        dedupe_key=f"cooccurrence.run_completed.{run.run_id}",
    )

    # Chain hub detection
    hub_enabled = AppSetting.objects.filter(
        key="cooccurrence.hub_detection_enabled"
    ).first()
    if not hub_enabled or hub_enabled.value.lower() != "false":
        detect_behavioral_hubs.delay()

    return {
        "status": "completed",
        "run_id": str(run.run_id),
        "sessions_processed": sessions_processed,
        "pairs_written": pairs_written,
        "ga4_rows_fetched": ga4_rows_fetched,
    }


@shared_task(
    name="cooccurrence.detect_behavioral_hubs", time_limit=1800, soft_time_limit=1740
)
def detect_behavioral_hubs() -> dict:
    """Run hub detection from existing co-occurrence data."""
    from apps.core.models import AppSetting
    from .services import detect_behavioral_hubs as _detect

    def _read_float(key: str, default: float) -> float:
        try:
            return float(AppSetting.objects.get(key=key).value)
        except (AppSetting.DoesNotExist, ValueError):
            return default

    def _read_int(key: str, default: int) -> int:
        try:
            return int(AppSetting.objects.get(key=key).value)
        except (AppSetting.DoesNotExist, ValueError):
            return default

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
    from .services import get_site_max_jaccard, compute_value_model_score

    settings = get_value_model_settings()
    if not settings.get("enabled", True):
        logger.info(
            "Value model disabled — skipping apply_value_model_scores for run %s",
            run_id,
        )
        return {"skipped": True, "reason": "value_model.enabled=false"}

    site_max_jaccard = get_site_max_jaccard()

    suggestions = list(
        Suggestion.objects.filter(pipeline_run_id=run_id).select_related(
            "destination", "host"
        )
    )

    if not suggestions:
        return {"updated": 0, "run_id": run_id}

    to_update = []
    for suggestion in suggestions:
        score, diagnostics = compute_value_model_score(
            suggestion=suggestion,
            settings=settings,
            site_max_jaccard=site_max_jaccard,
        )
        suggestion.score_value_model = score
        suggestion.value_model_diagnostics = diagnostics
        to_update.append(suggestion)

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
