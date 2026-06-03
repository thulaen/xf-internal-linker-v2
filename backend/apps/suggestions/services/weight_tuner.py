"""Weight tuner module for the suggestions app."""

import logging
import numpy as np
from datetime import timedelta
from django.utils import timezone
from scipy.optimize import minimize

from apps.suggestions.models import Suggestion, RankingChallenger
from apps.suggestions.weight_preset_service import get_current_weights

# OpenTelemetry tracer — defensive import so the module loads cleanly
# when the SDK is absent. The auto-instrumentation in
# `config.settings.base` covers Postgres queries from this file; this
# tracer adds a parent span for the whole tune-loop so the GlitchTip
# trace shows "tune started → collected N samples → L-BFGS-B optimised
# → returned challenger" as one navigable tree (added 2026-05-09 per
# AutoIssue #12).
try:
    from opentelemetry import trace as _otel_trace

    _tracer = _otel_trace.get_tracer(__name__)
except Exception:  # noqa: BLE001 — SDK absent; degrade to no-op tracer.
    class _NoopSpan:
        def set_attribute(self, *_args, **_kwargs) -> None: pass

    class _NoopTracer:
        from contextlib import contextmanager

        @contextmanager
        def start_as_current_span(self, _name: str):  # type: ignore[no-redef]
            yield _NoopSpan()

    _tracer = _NoopTracer()  # type: ignore[assignment]

logger = logging.getLogger(__name__)

_DRIFT_LIMIT_PER_RUN = 0.05
_WEIGHT_EPSILON = 1e-9

# Hard floor that the autotuner is forbidden to drive any weight below.
# Per DEFAULT-ON-RULE.md and the user's explicit safety request: the
# autotuner must never silently disable a feature by zeroing its weight.
# Empirical: smallest non-zero weight in the Recommended preset is 0.03,
# so 0.01 leaves the tuner room to nudge below current values without
# ever zeroing them. The simplex projection respects this floor too.
_WEIGHT_FLOOR = 0.01


def _emit_weight_tuner_event(
    event_type: str,
    title: str,
    message: str,
    severity: str = "info",
    **metadata,
) -> None:
    try:
        from apps.ops_feed.services import emit

        emit(
            event_type=event_type,
            plain_english=f"{title}: {message}",
            source="weight_tuner",
            severity=severity,
            related_entity_type="weight_tune_run",
            related_entity_id=str(metadata.get("run_id", "")),
            runtime_context=metadata,
        )
    except Exception:  # noqa: BLE001
        logger.debug("weight_tuner: operations-feed emit failed", exc_info=True)


def _normalize_weight_vector(weights: np.ndarray) -> np.ndarray:
    """Return a finite weight vector with sum 1.0."""
    values = np.asarray(weights, dtype=np.float64)
    # Phase 0.13: empty input would otherwise raise ZeroDivisionError on
    # the 1/len(values) fallback. An empty weight vector is a sensible
    # caller error (no signals to blend) so we return it unchanged.
    if values.size == 0:
        return values
    total = float(np.sum(values))
    if not np.isfinite(total) or total <= _WEIGHT_EPSILON:
        return np.full(len(values), 1.0 / len(values), dtype=np.float64)
    return values / total


def _project_to_bounded_simplex(
    weights: np.ndarray,
    lower_bounds: np.ndarray,
    upper_bounds: np.ndarray,
) -> np.ndarray:
    """Clamp weights to drift bounds while preserving a sum of 1.0."""
    projected = np.clip(
        np.asarray(weights, dtype=np.float64),
        lower_bounds,
        upper_bounds,
    )

    for _ in range(len(projected) * 2):
        residual = 1.0 - float(np.sum(projected))
        if abs(residual) <= _WEIGHT_EPSILON:
            break
        if residual > 0:
            capacity = upper_bounds - projected
            eligible = capacity > _WEIGHT_EPSILON
        else:
            capacity = projected - lower_bounds
            eligible = capacity > _WEIGHT_EPSILON

        total_capacity = float(np.sum(capacity[eligible]))
        if total_capacity <= _WEIGHT_EPSILON:
            break

        step = min(abs(residual), total_capacity)
        adjustment = np.zeros_like(projected)
        adjustment[eligible] = step * capacity[eligible] / total_capacity
        if residual > 0:
            projected += adjustment
        else:
            projected -= adjustment

    residual = 1.0 - float(np.sum(projected))
    if abs(residual) > _WEIGHT_EPSILON:
        if residual > 0:
            eligible = np.where((upper_bounds - projected) > _WEIGHT_EPSILON)[0]
        else:
            eligible = np.where((projected - lower_bounds) > _WEIGHT_EPSILON)[0]
        if len(eligible) > 0:
            idx = int(eligible[0])
            projected[idx] = min(
                upper_bounds[idx],
                max(lower_bounds[idx], projected[idx] + residual),
            )

    return projected


class WeightTuner:
    """FR-018: Python L-BFGS-B weight optimizer for the ranking blend.

    Pure-Python implementation per FR-018 spec. Finds optimal weights for
    the active feature blend by maximizing the likelihood of human
    approvals via ``scipy.optimize.minimize`` with bounded drift.

    FR-249 extension (2026-05-07) — when the
    ``pipeline.embedding_age_weight_in_composite`` AppSetting is enabled
    (default true), ``score_embedding_age`` joins the feature set as a
    5th tunable signal. The corresponding weight key is
    ``w_embedding_age`` and is auto-seeded into the Recommended preset
    at 0.05 (Liu 2009 §1.5.4 — small enough not to dominate, large
    enough to break ties between equally-scored candidates).

    Adding a new tunable signal in the future is a 4-line change:
    extend ``feature_keys`` + ``weight_keys`` + add a default into
    ``recommended_weights.py`` + ensure the matching ``score_*``
    column exists on ``Suggestion``. The L-BFGS-B objective and
    drift-bounded simplex projection both scale to N weights without
    further changes.
    """

    # Mapping from blend-weight key (e.g. "w_semantic") to its matching
    # feature column on the Suggestion model (e.g. "score_semantic").
    # Keep these in sync with each entry in tunable_registry.BLEND_WEIGHTS:
    # the registry stores the canonical weight keys; this map turns each
    # `w_X` into the corresponding `score_X` the tuner reads from the DB.
    _WEIGHT_TO_FEATURE: dict[str, str] = {
        "w_semantic": "score_semantic",
        "w_keyword": "score_keyword",
        "w_node": "score_node_affinity",
        "w_quality": "score_quality",
        # Conditional: registered in CONDITIONAL_BLEND_WEIGHTS, only
        # used when its enabling AppSetting is non-zero.
        "w_embedding_age": "score_embedding_age",
    }

    def __init__(self, lookback_days: int = 90):
        self.lookback_days = lookback_days
        self.weight_keys, self.feature_keys = self._load_active_weights()

    def _load_active_weights(self) -> tuple[list[str], list[str]]:
        """Walk the canonical registry to assemble (weight_keys, feature_keys).

        The unconditional set is `tunable_registry.BLEND_WEIGHTS` — those
        always participate. The conditional set
        `CONDITIONAL_BLEND_WEIGHTS` is added only when its enabling
        AppSetting is present and non-zero (cold-start safe: any read
        error leaves the tuner at the unconditional baseline).
        """
        from apps.suggestions.tunable_registry import (
            BLEND_WEIGHTS,
            CONDITIONAL_BLEND_WEIGHTS,
        )

        weight_keys: list[str] = list(BLEND_WEIGHTS.keys())
        feature_keys: list[str] = [
            self._WEIGHT_TO_FEATURE[k] for k in weight_keys
        ]
        # Conditional weights — guarded by a setting key.
        for w_key, (gate_key, _entry) in CONDITIONAL_BLEND_WEIGHTS.items():
            try:
                from apps.suggestions.recommended_weights import recommended_float

                gate_value = recommended_float(gate_key)
            except Exception:  # noqa: BLE001 — cold-start safe.
                continue
            if gate_value is None or float(gate_value) <= 0.0:
                continue
            feature = self._WEIGHT_TO_FEATURE.get(w_key)
            if feature is None:
                logger.warning(
                    "weight_tuner: conditional blend weight %s has no feature mapping in _WEIGHT_TO_FEATURE — skipping",
                    w_key,
                )
                continue
            weight_keys += [w_key]
            feature_keys += [feature]
        return weight_keys, feature_keys

    # Backwards-compatible alias kept for any caller that grepped this
    # name; the registry-driven `_load_active_weights` replaced it.
    def _maybe_add_fr249_age_decay(self) -> None:
        """Deprecated — registry-driven; retained as a no-op for callers."""
        # The conditional include for `w_embedding_age` is now handled
        # inside `_load_active_weights` via CONDITIONAL_BLEND_WEIGHTS.
        return

    def run(self, run_id: str) -> RankingChallenger | None:
        """Execute the tuning loop and return a new RankingChallenger if improved."""
        with _tracer.start_as_current_span("autotuner.weight_tuner.run") as span:
            span.set_attribute("autotuner.run_id", run_id)
            span.set_attribute("autotuner.lookback_days", self.lookback_days)
            span.set_attribute("autotuner.weight_keys", ",".join(self.weight_keys))
            return self._run_traced(run_id, span)

    def _run_traced(self, run_id: str, span) -> RankingChallenger | None:
        """The original `run` body — extracted so the span wraps it."""
        _emit_weight_tuner_event(
            "meta_algorithm.tune_started",
            "Weight tuning started",
            "The ranking weight tuner started looking for a better scoring mix.",
            run_id=run_id,
            lookback_days=self.lookback_days,
        )
        # 1. Collect Data
        cutoff = timezone.now() - timedelta(days=self.lookback_days)
        samples = Suggestion.objects.filter(
            status__in=["approved", "rejected"], reviewed_at__gte=cutoff
        ).values(*self.feature_keys, "score_final", "status")

        if len(samples) < 50:
            logger.info(
                "[WeightTuner] Insufficient samples (%d) for tuning.", len(samples)
            )
            _emit_weight_tuner_event(
                "meta_algorithm.tune_skipped",
                "Weight tuning skipped",
                "The tuner did not have enough reviewed suggestions to make a safe change.",
                "warning",
                run_id=run_id,
                sample_count=len(samples),
            )
            return None

        X = np.asarray(
            [
                tuple(float(s[k] or 0) for k in self.feature_keys)
                for s in samples
            ],
            dtype=np.float64,
        )
        y = np.asarray(
            [1 if s["status"] == "approved" else 0 for s in samples],
            dtype=np.float64,
        )
        score_finals = np.asarray(
            [float(s["score_final"] or 0) for s in samples],
            dtype=np.float64,
        )

        # 2. Get Current Weights
        curr_vals = get_current_weights()
        raw_init = np.array([float(curr_vals.get(k, 0.25)) for k in self.weight_keys])
        w_init = _normalize_weight_vector(raw_init)

        # 3. Optimize using L-BFGS-B
        # Constraints: sum(w) = 1, each w in [0, 1]
        # Drift limit: abs(w_new - w_old) <= 0.05

        # Per DEFAULT-ON-RULE.md: the autotuner must never zero a weight.
        # Floor every lower bound at _WEIGHT_FLOOR (0.01) so even a feature
        # that started at 0.04 cannot be driven to zero by ±0.05 drift.
        lower_bounds = np.maximum(_WEIGHT_FLOOR, w_init - _DRIFT_LIMIT_PER_RUN)
        upper_bounds = np.minimum(1.0, w_init + _DRIFT_LIMIT_PER_RUN)
        bounds = list(zip(lower_bounds, upper_bounds, strict=True))

        # Pre-compute remainder: what the other 50+ ranking signals contributed to score_final.
        # This ensures we optimize actual ranker quality, not a 4-number global summary.
        remainders = score_finals - np.dot(X, w_init)

        def objective(w, X, y, remainders):
            # Normalize w to sum to 1 internally for the loss calculation
            # to avoid non-convexity issues if we don't use strict equality constraint
            w_norm = _normalize_weight_vector(w)
            z = np.dot(X, w_norm) + remainders
            # Center of quality threshold is ~0.7 for strong suggestions
            logits = 15 * (z - 0.7)
            probs = 1 / (1 + np.exp(-logits))
            # Binary Cross Entropy
            loss = -np.mean(
                y * np.log(probs + 1e-9) + (1 - y) * np.log(1 - probs + 1e-9)
            )
            # Penalty for drift from initial weights (regularization)
            drift_penalty = 0.1 * np.sum((w - w_init) ** 2)
            return loss + drift_penalty

        res = minimize(
            objective,
            w_init,
            args=(X, y, remainders),
            method="L-BFGS-B",
            bounds=bounds,
        )

        if not res.success:
            logger.warning("[WeightTuner] Optimization failed: %s", res.message)
            _emit_weight_tuner_event(
                "meta_algorithm.tune_failed",
                "Weight tuning failed",
                "The tuner could not finish its optimisation pass.",
                "warning",
                run_id=run_id,
                reason=str(res.message),
            )
            return None

        w_opt = _project_to_bounded_simplex(res.x, lower_bounds, upper_bounds)

        # 4. Create Challenger.
        # Use ``len(self.weight_keys)`` instead of a hardcoded 4 so adding a
        # 5th tuneable weight in the future doesn't silently truncate the
        # candidate dict. Today weight_keys is always length-4 per the
        # FR-018 spec (semantic, keyword, node, quality).
        n_weights = len(self.weight_keys)
        candidate = {
            self.weight_keys[i]: round(float(w_opt[i]), 4) for i in range(n_weights)
        }
        baseline = {
            self.weight_keys[i]: round(float(w_init[i]), 4) for i in range(n_weights)
        }

        # Check if change is significant (> 0.001)
        if np.allclose(w_init, w_opt, atol=1e-3):
            logger.info("[WeightTuner] No significant weight improvement found.")
            _emit_weight_tuner_event(
                "meta_algorithm.tune_finished",
                "Weight tuning finished with no change",
                "The tuner checked the latest feedback and found no safer improvement.",
                "info",
                run_id=run_id,
                sample_count=len(samples),
            )
            return None

        # Compute predicted vs champion quality scores using the same objective
        # the optimizer minimised. Both numbers come from the same function so
        # the SPRT comparator in evaluate_weight_challenger sees a fair ratio.
        # quality = 1 / (1 + loss) is bounded in (0, 1] and monotonically
        # decreasing in loss.
        champion_loss = float(objective(w_init, X, y, remainders))
        candidate_loss = float(objective(w_opt, X, y, remainders))
        champion_quality = 1.0 / (1.0 + champion_loss)
        predicted_quality = 1.0 / (1.0 + candidate_loss)

        challenger = RankingChallenger.objects.create(
            run_id=run_id,
            status="pending",
            candidate_weights=candidate,
            baseline_weights=baseline,
            predicted_quality_score=predicted_quality,
            champion_quality_score=champion_quality,
        )
        logger.info(
            "[WeightTuner] Created challenger %s for run_id %s "
            "(samples=%d, approval_rate=%.3f, iterations=%d, "
            "champion_loss=%.4f, candidate_loss=%.4f).",
            challenger.pk,
            run_id,
            len(y),
            float(np.mean(y)),
            res.nit,
            champion_loss,
            candidate_loss,
        )
        _emit_weight_tuner_event(
            "meta_algorithm.tune_finished",
            "Weight tuning created a challenger",
            "The tuner found a candidate scoring mix for review.",
            "success",
            run_id=run_id,
            challenger_id=str(challenger.pk),
            sample_count=len(samples),
            champion_loss=champion_loss,
            candidate_loss=candidate_loss,
        )
        return challenger
