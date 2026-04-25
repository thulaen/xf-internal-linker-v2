"""Producer + read API for pick #52 Adaptive Conformal Inference.

Pick #52 wraps pick #50 split-conformal with online α adjustment so
long-run coverage stays at the target even when the data
distribution drifts. The math lives in
:mod:`apps.pipeline.services.adaptive_conformal_inference`. This
module is the producer + persistence layer:

- :func:`update_alpha_from_recent_outcomes` — pull recently reviewed
  Suggestions whose ``confidence_lower_bound`` / ``upper_bound``
  were populated, compute "was the label inside the predicted
  interval?" per row, feed those to the
  :class:`AdaptiveConformalInference` updater, persist the new α.
  Cold-start safe: zero recent outcomes → α unchanged.
- :func:`load_alpha` — read the persisted current α (with the
  static target as the cold-start fallback). The conformal
  scheduled job calls this and feeds the result into
  :func:`apps.pipeline.services.conformal_predictor.fit_and_persist_from_history`
  on each refit, so the calibration adapts under drift without
  breaking the cold-start path.

The window of observations is **not** persisted — it's reconstituted
from the last N reviewed Suggestions on each scheduled run, which
gives the same numerics as a deque-backed online updater while
staying stateless across process restarts.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from .adaptive_conformal_inference import (
    AdaptiveConformalInference,
    DEFAULT_CLIP_MAX,
    DEFAULT_CLIP_MIN,
    DEFAULT_LEARNING_RATE_GAMMA,
    DEFAULT_TARGET_ALPHA,
    DEFAULT_WINDOW_SIZE,
)

logger = logging.getLogger(__name__)


KEY_CURRENT_ALPHA = "adaptive_conformal_inference.current_alpha"
KEY_TARGET_ALPHA = "adaptive_conformal_inference.target_alpha"
KEY_OBSERVATIONS = "adaptive_conformal_inference.observations"
KEY_OBSERVED_COVERAGE = "adaptive_conformal_inference.observed_coverage"
KEY_LAST_UPDATED = "adaptive_conformal_inference.last_updated"


@dataclass(frozen=True)
class AciUpdateResult:
    """Audit trail for the scheduled-job UI."""

    observations_processed: int
    previous_alpha: float
    current_alpha: float
    observed_coverage: float


def load_alpha(*, default: float = DEFAULT_TARGET_ALPHA) -> float:
    """Return the persisted ACI-adapted α, or *default* on cold start.

    The conformal_predictor.fit_and_persist_from_history call reads
    this and uses it as its ``alpha`` parameter, so each weekly
    refit absorbs the latest drift correction.
    """
    try:
        from apps.core.models import AppSetting
    except Exception:  # pragma: no cover — Django not initialised
        return default
    row = AppSetting.objects.filter(key=KEY_CURRENT_ALPHA).first()
    if row is None:
        return default
    try:
        return float(row.value)
    except (TypeError, ValueError):
        logger.warning("adaptive_conformal: malformed alpha row, using default")
        return default


def update_alpha_from_recent_outcomes(
    *,
    target_alpha: float = DEFAULT_TARGET_ALPHA,
    learning_rate_gamma: float = DEFAULT_LEARNING_RATE_GAMMA,
    window_size: int = DEFAULT_WINDOW_SIZE,
    clip_min: float = DEFAULT_CLIP_MIN,
    clip_max: float = DEFAULT_CLIP_MAX,
) -> AciUpdateResult:
    """Update the persisted α from the last ``window_size`` reviewed
    Suggestions whose conformal bounds were populated.

    "Was covered" = the operator's binary label (1.0 for approved/
    applied, 0.0 for rejected) fell inside ``[confidence_lower_bound,
    confidence_upper_bound]``. Pre-pick-50 rows have NULL bounds and
    are skipped — they predate calibration so coverage isn't defined
    for them.
    """
    from django.utils import timezone

    from apps.core.models import AppSetting
    from apps.suggestions.models import Suggestion

    # Load the previous α so the updater continues from where the
    # last run left off (Gibbs-Candès Algorithm 1 is stateful).
    previous_alpha = load_alpha(default=target_alpha)

    aci = AdaptiveConformalInference(
        target_alpha=target_alpha,
        learning_rate_gamma=learning_rate_gamma,
        window_size=window_size,
        clip_min=clip_min,
        clip_max=clip_max,
    )
    # Seed the updater's state with the persisted α so subsequent
    # observations move the trajectory rather than restarting at the
    # static target.
    aci.current_alpha = max(clip_min, min(clip_max, previous_alpha))

    # Pull the most recent reviewed Suggestions whose bounds are set.
    rows = list(
        Suggestion.objects.filter(
            status__in=["approved", "applied", "verified", "rejected", "declined", "dismissed", "superseded"],
            confidence_lower_bound__isnull=False,
            confidence_upper_bound__isnull=False,
        )
        .order_by("-updated_at")
        .values_list(
            "score_final", "status", "confidence_lower_bound", "confidence_upper_bound"
        )[:window_size]
    )

    positive_statuses = {"approved", "applied", "verified"}
    observations_processed = 0
    for score, status, lower, upper in rows:
        if score is None or lower is None or upper is None:
            continue
        label = 1.0 if status in positive_statuses else 0.0
        was_covered = lower <= label <= upper
        aci.update(was_covered)
        observations_processed += 1

    # Persist the four ACI snapshot rows.
    snapshot = aci.snapshot()
    fitted_at = timezone.now().isoformat()
    for key, value in (
        (KEY_CURRENT_ALPHA, str(snapshot["current_alpha"])),
        (KEY_TARGET_ALPHA, str(snapshot["target_alpha"])),
        (KEY_OBSERVATIONS, str(int(snapshot["observations"]))),
        (KEY_OBSERVED_COVERAGE, str(snapshot["observed_coverage"])),
        (KEY_LAST_UPDATED, fitted_at),
    ):
        AppSetting.objects.update_or_create(
            key=key,
            defaults={
                "value": value,
                "description": (
                    "Pick #52 Adaptive Conformal Inference state — "
                    "Gibbs-Candès 2021 online α tracker."
                ),
            },
        )

    return AciUpdateResult(
        observations_processed=observations_processed,
        previous_alpha=previous_alpha,
        current_alpha=aci.current_alpha,
        observed_coverage=aci.observed_coverage,
    )
