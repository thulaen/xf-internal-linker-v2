import logging
import numpy as np
from datetime import timedelta
from django.utils import timezone
from scipy.optimize import minimize

from apps.suggestions.models import Suggestion, RankingChallenger
from apps.suggestions.weight_preset_service import get_current_weights

logger = logging.getLogger(__name__)


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
        w_init = np.array([float(curr_vals.get(k, 0.25)) for k in self.weight_keys])

        # 3. Optimize using L-BFGS-B
        # Constraints: sum(w) = 1, each w in [0, 1]
        # Drift limit: abs(w_new - w_old) <= 0.05

        bounds = []
        for w in w_init:
            bounds.append((max(0.0, w - 0.05), min(1.0, w + 0.05)))

        # Pre-compute remainder: what the other 50+ ranking signals contributed to score_final.
        # This ensures we optimize actual ranker quality, not a 4-number global summary.
        remainders = score_finals - np.dot(X, w_init)

        def objective(w, X, y, remainders):
            # Normalize w to sum to 1 internally for the loss calculation
            # to avoid non-convexity issues if we don't use strict equality constraint
            w_norm = w / (np.sum(w) + 1e-9)
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

        res = minimize(objective, w_init, args=(X, y, remainders), method="L-BFGS-B", bounds=bounds)

        if not res.success:
            logger.warning("[WeightTuner] Optimization failed: %s", res.message)
            return None

        w_opt = res.x
        w_opt = w_opt / np.sum(w_opt)  # Final normalization

        # 4. Create Challenger
        candidate = {self.weight_keys[i]: round(float(w_opt[i]), 4) for i in range(4)}
        baseline = {self.weight_keys[i]: float(w_init[i]) for i in range(4)}

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
        candidate_loss = float(res.fun)
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
