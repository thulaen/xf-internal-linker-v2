from __future__ import annotations
import logging
import time
import uuid
import traceback
from datetime import date, timedelta
from typing import Any

from celery import shared_task
from django.db import DatabaseError, connection
from django.utils import timezone

from apps.pipeline.decorators import with_weight_lock
from apps.core.helpers import HelperConstraint
from apps.notifications.services import emit_operator_alert
from apps.notifications.models import OperatorAlert

logger = logging.getLogger(__name__)

_RUN_ID_PREVIEW_LEN = 16
_PCT_MULTIPLIER = 100
_GSC_SPIKE_COOLDOWN = 86400

# ---------------------------------------------------------------------------
# Part 8 — FR-018 Python auto-tune tasks
# ---------------------------------------------------------------------------

@shared_task(
    bind=True,
    name="pipeline.monthly_weight_tune",
    time_limit=600,
    soft_time_limit=540,
    acks_late=True,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=240,
)
@with_weight_lock("medium")
def monthly_weight_tune(self):
    """Trigger an FR-018 weight-tune run via the Python WeightTuner, then evaluate."""
    if not connection.in_atomic_block:
        connection.close()
    import uuid as _uuid
    from apps.audit.models import ErrorLog
    from apps.suggestions.services.weight_tuner import WeightTuner

    run_id = str(_uuid.uuid4())
    try:
        tuner = WeightTuner(lookback_days=90)
        challenger = tuner.run(run_id=run_id)
        if challenger:
            logger.info("[monthly_weight_tune] Native tuner found improvement. run_id=%s", run_id)
            evaluate_weight_challenger.delay(run_id=run_id)
            return {"status": "submitted", "run_id": run_id, "challenger_id": str(challenger.pk)}
        else:
            logger.info("[monthly_weight_tune] No improvement found by native tuner.")
            return {"status": "skipped", "run_id": run_id}
    except (DatabaseError, TimeoutError, MemoryError, ValueError):
        raw = traceback.format_exc()
        logger.exception("[monthly_weight_tune] Failed: %s", raw)
        ErrorLog.objects.create(
            job_type="auto_tune_weights",
            step="monthly_weight_tune",
            error_message="Weight-tune task failed.",
            raw_exception=raw,
            why="The monthly auto-tune task raised an unexpected exception.",
        )
        return {"status": "error"}

@shared_task(
    bind=True,
    name="pipeline.monthly_meta_tune",
    time_limit=600,
    soft_time_limit=540,
    acks_late=True,
)
@HelperConstraint(
    cpu_intensive=True,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=512,
    expected_seconds_p50=240,
)
@with_weight_lock("medium")
def monthly_meta_tune(self):
    """Trigger an FR-018 meta-algorithm tune run."""
    if not connection.in_atomic_block:
        connection.close()
    import uuid as _uuid

    from apps.suggestions.services.meta_tuner import MetaAlgorithmTuner
    from apps.suggestions.models import RankingChallenger
    from apps.suggestions.weight_preset_service import get_current_weights

    run_id = str(_uuid.uuid4())
    try:
        tuner = MetaAlgorithmTuner()
        proposed = tuner.propose()
        if not proposed:
            logger.info("[monthly_meta_tune] No improvement found.")
            return {"status": "skipped", "run_id": run_id}
        baseline = get_current_weights()
        challenger = RankingChallenger.objects.create(
            run_id=run_id,
            kind="meta_algorithm",
            status="pending",
            candidate_weights={key: str(value) for key, value in proposed.items()},
            baseline_weights={key: str(baseline.get(key, "")) for key in proposed},
        )
        logger.info("[monthly_meta_tune] Created meta challenger. run_id=%s", run_id)
        return {"status": "created", "run_id": run_id, "challenger_id": str(challenger.pk)}
    except (DatabaseError, TimeoutError, MemoryError, ValueError):
        raw = traceback.format_exc()
        logger.exception("[monthly_meta_tune] Failed: %s", raw)
        _record_meta_tune_failure(raw)
        return {"status": "error"}

def _record_meta_tune_failure(raw: str) -> None:
    from apps.audit.models import ErrorLog
    ErrorLog.objects.create(
        job_type="auto_tune_meta_algorithms",
        step="monthly_meta_tune",
        error_message="Meta-algorithm tune task failed.",
        raw_exception=raw,
        why="The monthly meta-tune task raised an unexpected exception.",
    )

@shared_task(bind=True, name="pipeline.evaluate_meta_challenger", time_limit=300)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=60,
)
def evaluate_meta_challenger(self, run_id: str):
    """Evaluate and optionally promote a meta-algorithm challenger."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.suggestions.models import RankingChallenger
    challenger = RankingChallenger.objects.filter(
        run_id=run_id, kind="meta_algorithm"
    ).first()
    if not challenger:
        logger.error("[evaluate_meta_challenger] Challenger %s not found.", run_id)
        return {"status": "not_found", "run_id": run_id}
    try:
        from apps.suggestions.services.meta_evaluator import evaluate_and_promote
    except ImportError:
        logger.info("[evaluate_meta_challenger] Meta evaluator is not installed yet.")
        return {"status": "deferred", "run_id": run_id}
    evaluate_and_promote(challenger)
    return {"status": "evaluated", "run_id": run_id}

@shared_task(bind=True, name="pipeline.evaluate_weight_challenger", time_limit=300)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=60,
)
def evaluate_weight_challenger(self, *, run_id: str):
    """Evaluate and optionally promote a weight challenger."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.suggestions.models import RankingChallenger
    try:
        challenger = RankingChallenger.objects.filter(
            run_id=run_id, kind="weights"
        ).first()
        if not challenger:
            logger.error("[evaluate_weight_challenger] Challenger %s not found.", run_id)
            return {"status": "not_found", "run_id": run_id}
        try:
            from apps.suggestions.services.weight_evaluator import evaluate_and_promote
        except ImportError:
            logger.info("[evaluate_weight_challenger] Weight evaluator is not installed yet.")
            return {"status": "deferred", "run_id": run_id}
        evaluate_and_promote(challenger)
        return {"status": "evaluated", "run_id": run_id}
    except Exception:
        logger.exception("[evaluate_weight_challenger] Failed for run_id %s", run_id)
        return {"status": "error", "run_id": run_id}

@shared_task(name="pipeline.check_weight_rollback", time_limit=300)
@HelperConstraint(
    cpu_intensive=False,  # mostly aggregate/rollback queries
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=60,
)
def check_weight_rollback():
    """Periodic task to detect and roll back weight regressions via GSC."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.suggestions.models import RankingChallenger
    challengers = RankingChallenger.objects.filter(
        status="promoted", kind="weights"
    ).order_by("-updated_at")[:5]
    for challenger in challengers:
        _check_one_challenger_rollback(challenger)

_REGRESSION_THRESHOLD = 0.85
_MIN_PRE_CLICKS_FOR_ROLLBACK = 50

def _check_one_challenger_rollback(challenger) -> None:
    promoted_at = challenger.updated_at.date()
    pre_clicks, post_clicks = _aggregate_gsc_click_windows(
        pre=(promoted_at - timedelta(days=14), promoted_at - timedelta(days=1)),
        post=(promoted_at, promoted_at + timedelta(days=13)),
    )
    if pre_clicks < _MIN_PRE_CLICKS_FOR_ROLLBACK:
        return
    ratio = post_clicks / pre_clicks
    if ratio >= _REGRESSION_THRESHOLD:
        return
    _execute_rollback(challenger, ratio)

def _aggregate_gsc_click_windows(pre: tuple, post: tuple) -> tuple[int, int]:
    from django.db.models import Sum
    from apps.analytics.models import GSCDailyPerformance
    def _sum(start, end) -> int:
        return GSCDailyPerformance.objects.filter(date__range=(start, end)).aggregate(total=Sum("clicks"))["total"] or 0
    return _sum(*pre), _sum(*post)

def _execute_rollback(challenger, ratio: float) -> None:
    from django.db import transaction
    from apps.suggestions.weight_preset_service import apply_weights, get_current_weights, write_history
    if not challenger.baseline_weights:
        return
    previous_weights = get_current_weights()
    rollback_target = dict(previous_weights)
    for key, val in challenger.baseline_weights.items():
        rollback_target[key] = str(val)
    with transaction.atomic():
        apply_weights(rollback_target)
    new_weights = get_current_weights()
    write_history(
        source="auto_tune",
        previous_weights=previous_weights,
        new_weights=new_weights,
        reason=f"FR-018 auto-rollback: challenger {challenger.run_id[:_RUN_ID_PREVIEW_LEN]} caused GSC regression (ratio={ratio:.2f}).",
        r_run_id=challenger.run_id,
    )
    challenger.status = "rolled_back"
    challenger.save(update_fields=["status", "updated_at"])

@shared_task(bind=True, name="pipeline.check_gsc_spikes", time_limit=300)
@HelperConstraint(
    cpu_intensive=False,
    gpu_required=False,
    storage_writes_to="postgres_main",
    ram_peak_mb=128,
    expected_seconds_p50=60,
)
def check_gsc_spikes(self) -> dict:
    """Detect search demand spikes and alert the operator."""
    if not connection.in_atomic_block:
        connection.close()
    from apps.content.models import ContentItem
    spikes_found = 0
    for item in ContentItem.objects.filter(is_active=True):
        if _check_one_item_spike(item):
            spikes_found += 1
    return {"spikes_found": spikes_found}

def _check_one_item_spike(item) -> bool:
    try:
        from apps.analytics.spike_detector import detect_spike  # type: ignore[import-not-found]
    except ImportError:
        logger.debug(
            "check_gsc_spikes: spike detector not installed; skipping item %s",
            getattr(item, "pk", "?"),
        )
        return False
    spike = detect_spike(item)
    if not spike:
        return False
    try:
        severity = "high" if spike["clk_lift"] > 0.5 else "medium"
        message = f"Page '{item.title}' saw a {spike['clk_lift']*100:.1f}% click lift."
        today = date.today()
        emit_operator_alert(
            event_type="analytics.gsc_spike",
            severity=severity,
            title="Google search demand spiked",
            message=message,
            source_area=OperatorAlert.AREA_ANALYTICS,
            dedupe_key=f"analytics.gsc_spike:{item.pk}:{today.isoformat()}",
            related_object_type="ContentItem",
            related_object_id=str(item.pk),
            related_route="/analytics",
            payload={"content_item_id": item.pk, "title": item.title},
            cooldown_seconds=_GSC_SPIKE_COOLDOWN,
        )
        return True
    except Exception:
        logger.warning("check_gsc_spikes: failed to emit alert for item %s", item.pk, exc_info=True)
        return False
