import logging
import numpy as np
from datetime import timedelta
from django.utils import timezone
from scipy.optimize import minimize

from apps.suggestions.models import Suggestion, RankingChallenger
from apps.suggestions.weight_preset_service import get_current_weights

logger = logging.getLogger(__name__)

_DRIFT_LIMIT_PER_RUN = 0.05
_WEIGHT_EPSILON = 1e-9


def _normalize_weight_vector(weights: np.ndarray) -> np.ndarray:
    """Return a finite weight vector with sum 1.0."""
    values = np.asarray(weights, dtype=np.float64)
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
    (semantic, keyword, node, quality) by maximizing the likelihood of human
    approvals via ``scipy.optimize.minimize`` with bounded drift.
    """

    def __init__(self, lookback_days: int = 90):
        self.lookback_days = lookback_days
        self.feature_keys = [
            "score_semantic",
            "score_keyword",
            "score_node_affinity",
            "score_quality",
        ]
        self.weight_keys = ["w_semantic", "w_keyword", "w_node", "w_quality"]

    def run(self, run_id: str) -> RankingChallenger | None:
        """Execute the tuning loop and return a new RankingChallenger if improved."""
        # 1. Collect Data
        cutoff = timezone.now() - timedelta(days=self.lookback_days)
        samples = Suggestion.objects.filter(
            status__in=["approved", "rejected"], reviewed_at__gte=cutoff
        ).values(*self.feature_keys, "score_final", "status")

        if len(samples) < 50:
            logger.info(
                "[WeightTuner] Insufficient samples (%d) for tuning.", len(samples)
            )
            return None

        X = []
        y = []
        score_finals = []
        for s in samples:
            X.append([float(s[k] or 0) for k in self.feature_keys])
            y.append(1 if s["status"] == "approved" else 0)
            score_finals.append(float(s["score_final"] or 0))

        X = np.array(X)
        y = np.array(y)
        score_finals = np.array(score_finals)

        # 2. Get Current Weights
        curr_vals = get_current_weights()
        raw_init = np.array([float(curr_vals.get(k, 0.25)) for k in self.weight_keys])
        w_init = _normalize_weight_vector(raw_init)

        # 3. Optimize using L-BFGS-B
        # Constraints: sum(w) = 1, each w in [0, 1]
        # Drift limit: abs(w_new - w_old) <= 0.05

        lower_bounds = np.maximum(0.0, w_init - _DRIFT_LIMIT_PER_RUN)
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
            return None

        w_opt = _project_to_bounded_simplex(res.x, lower_bounds, upper_bounds)

        # 4. Create Challenger
        candidate = {self.weight_keys[i]: round(float(w_opt[i]), 4) for i in range(4)}
        baseline = {self.weight_keys[i]: round(float(w_init[i]), 4) for i in range(4)}

        # Check if change is significant (> 0.001)
        if np.allclose(w_init, w_opt, atol=1e-3):
            logger.info("[WeightTuner] No significant weight improvement found.")
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
        return challenger
