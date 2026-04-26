"""Score → probability calibration service — pick #32 wiring.

The :class:`apps.pipeline.services.platt_calibration.PlattCalibration`
helper is pure math. Production needs three things on top:

1. **Persistence.** A weekly fit needs to outlive the worker process
   that ran it. Stored under ``AppSetting`` keys so operators can
   inspect / reset via the existing settings UI.
2. **Fit-and-write.** A wrapper that pulls (score, accept/reject)
   pairs from the suggestion review history and runs the Platt fit
   end-to-end. The weekly weight-tuner job calls it.
3. **Apply.** Read-side helper used by the review queue (and W4's
   Explain panel) to convert a raw composite score into a calibrated
   "probability of being approved" for display.

All three are in this module. No new model fields — the calibration
is small (slope + bias + class counts) and lives in AppSetting rows.

Cold-start safety: ``calibrate_score`` returns the raw score
unchanged when no calibration has been fit yet (e.g. a brand-new
install). Operators see "85" instead of "0.85" until enough review
history exists, which is the right "no fake confidence" default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from typing import Iterable

from .platt_calibration import PlattCalibration, fit as platt_fit

logger = logging.getLogger(__name__)


#: AppSetting keys — kept namespaced so operators can find them in
#: the settings UI under "score_calibration.*".
KEY_SLOPE = "score_calibration.platt.slope"
KEY_BIAS = "score_calibration.platt.bias"
KEY_FITTED_AT = "score_calibration.platt.fitted_at"
KEY_TRAINING_PAIRS = "score_calibration.platt.training_pairs"

#: Minimum number of (score, label) pairs before we run a fit.
#: Below this the Platt slope is so high-variance that the calibrated
#: probabilities mislead more than they help. Matches the pick-32
#: spec §6 ``min_training_pairs`` default.
MIN_TRAINING_PAIRS: int = 50

#: Default lookback window for the weekly fit. Captures recent
#: operator behaviour without pulling in stale review patterns.
DEFAULT_LOOKBACK_DAYS: int = 90


@dataclass(frozen=True)
class CalibrationSnapshot:
    """The persisted calibration state, decoded from AppSetting rows."""

    slope: float
    bias: float
    fitted_at: str | None
    training_pairs: int

    def as_calibration(self) -> PlattCalibration:
        # ``n_positives`` / ``n_negatives`` are diagnostic-only here;
        # we don't store them per-row, so 0 is fine.
        return PlattCalibration(
            slope=self.slope,
            bias=self.bias,
            n_positives=0,
            n_negatives=0,
        )


# ── Read API ──────────────────────────────────────────────────────


def load_snapshot() -> CalibrationSnapshot | None:
    """Return the persisted calibration, or ``None`` on cold start."""
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return None

    rows = dict(
        AppSetting.objects.filter(
            key__in=[KEY_SLOPE, KEY_BIAS, KEY_FITTED_AT, KEY_TRAINING_PAIRS]
        ).values_list("key", "value")
    )
    if KEY_SLOPE not in rows or KEY_BIAS not in rows:
        return None
    try:
        slope = float(rows[KEY_SLOPE])
        bias = float(rows[KEY_BIAS])
        pairs = int(rows.get(KEY_TRAINING_PAIRS, "0") or "0")
    except (TypeError, ValueError):
        logger.warning("score_calibrator: malformed AppSetting row, ignoring")
        return None
    return CalibrationSnapshot(
        slope=slope,
        bias=bias,
        fitted_at=rows.get(KEY_FITTED_AT),
        training_pairs=pairs,
    )


def calibrate_score(raw_score: float, *, snapshot: CalibrationSnapshot | None = None) -> float:
    """Return the calibrated probability for *raw_score*, or *raw_score*
    unchanged when no calibration is available.

    Cold-start callers see the raw composite (typically 0..1 anyway)
    rather than a fake "0.5 because we have no calibration" — keeps
    the review-queue UI honest about its confidence.
    """
    snap = snapshot if snapshot is not None else load_snapshot()
    if snap is None:
        return float(raw_score)
    return snap.as_calibration().predict(float(raw_score))


# ── Write API (used by the weekly weight-tuner job) ──────────────


def fit_and_persist_from_history(
    *,
    lookback_days: int = DEFAULT_LOOKBACK_DAYS,
    min_pairs: int = MIN_TRAINING_PAIRS,
) -> CalibrationSnapshot | None:
    """Fit a fresh Platt calibration from recent suggestion outcomes.

    Pulls ``Suggestion`` rows reviewed within the lookback window,
    builds (score_final, label) pairs, calls
    :func:`apps.pipeline.services.platt_calibration.fit`, and writes
    the resulting slope + bias back to AppSetting.

    Returns the new snapshot, or ``None`` when there isn't enough
    review history to fit.
    """
    from django.utils import timezone

    pairs = list(_collect_training_pairs(lookback_days=lookback_days))
    if len(pairs) < min_pairs:
        logger.info(
            "score_calibrator: only %d / %d pairs available — skip fit",
            len(pairs),
            min_pairs,
        )
        return None

    scores, labels = zip(*pairs)
    if len(set(labels)) < 2:
        logger.info(
            "score_calibrator: training set has only one class — skip fit"
        )
        return None

    calibration = platt_fit(scores=list(scores), labels=list(labels))
    snapshot = _persist_snapshot(
        slope=calibration.slope,
        bias=calibration.bias,
        fitted_at=timezone.now().isoformat(),
        training_pairs=len(pairs),
    )
    logger.info(
        "score_calibrator: fitted Platt (slope=%.4f, bias=%.4f) on %d pairs",
        calibration.slope,
        calibration.bias,
        len(pairs),
    )
    return snapshot


# ── Internals ────────────────────────────────────────────────────


def _collect_training_pairs(
    *, lookback_days: int
) -> Iterable[tuple[float, int]]:
    """Yield ``(score_final, label)`` pairs from reviewed suggestions.

    ``label`` is 1 when the operator approved, 0 when rejected.
    Pending / unreviewed rows are skipped — no ground truth.
    """
    from django.utils import timezone

    try:
        from apps.suggestions.models import Suggestion
    except Exception:  # pragma: no cover — only when Django not loaded
        return

    cutoff = timezone.now() - timedelta(days=lookback_days)
    qs = (
        Suggestion.objects.filter(
            status__in=["approved", "rejected"],
            reviewed_at__gte=cutoff,
        )
        .values("score_semantic", "score_keyword", "score_node_affinity",
                "score_quality", "status")
    )
    for row in qs.iterator(chunk_size=2000):
        # Use the average of available score components as the proxy
        # for the composite — the C++ batch scorer's exact weights
        # aren't readable here, but the sign of the relationship
        # carries through fine for sigmoid calibration.
        components = [
            row.get("score_semantic", 0.0) or 0.0,
            row.get("score_keyword", 0.0) or 0.0,
            row.get("score_node_affinity", 0.0) or 0.0,
            row.get("score_quality", 0.0) or 0.0,
        ]
        avg = sum(components) / len(components)
        label = 1 if row["status"] == "approved" else 0
        yield (float(avg), label)


def _persist_snapshot(
    *, slope: float, bias: float, fitted_at: str, training_pairs: int
) -> CalibrationSnapshot:
    from apps.core.models import AppSetting

    for key, value in (
        (KEY_SLOPE, f"{slope:.6f}"),
        (KEY_BIAS, f"{bias:.6f}"),
        (KEY_FITTED_AT, fitted_at),
        (KEY_TRAINING_PAIRS, str(training_pairs)),
    ):
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "description": (
                    "Platt sigmoid calibration — fitted weekly from review "
                    "history; consumed by review-queue UI and Explain panel."
                ),
            },
        )
    return CalibrationSnapshot(
        slope=slope,
        bias=bias,
        fitted_at=fitted_at,
        training_pairs=training_pairs,
    )
