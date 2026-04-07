"""FR-013 Feedback-Driven Explore/Exploit Reranker.

This service implements a post-ranking layer that optimizes suggestion quality using 
historical reviewer feedback. It uses Bayesian Smoothing for Exploitation 
(Scope-to-Scope approval rates) and UCB1 for Exploration (boosting sparse data areas).
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import numpy as np
from django.db.models import Count, Q

try:
    from extensions import feedrerank
    HAS_CPP_EXT = True
except ImportError:
    HAS_CPP_EXT = False

from apps.suggestions.recommended_weights import recommended_bool, recommended_float

if TYPE_CHECKING:
    from apps.pipeline.services.ranker import ScoredCandidate


@dataclass(frozen=True, slots=True)
class FeedbackRerankSettings:
    """Settings controlling the Explore/Exploit reranker."""

    enabled: bool = recommended_bool("explore_exploit.enabled")
    ranking_weight: float = recommended_float("explore_exploit.ranking_weight")
    exploration_rate: float = recommended_float("explore_exploit.exploration_rate")  # k factor in UCB1 sqrt(k * ln(N)/n)
    alpha_prior: float = 1.0       # Bayesian smoothing alpha (prior approved)
    beta_prior: float = 1.0        # Bayesian smoothing beta (prior rejected)


class FeedbackRerankService:
    """Learns from Suggestion status history to bias future rankings."""

    def __init__(self, settings: FeedbackRerankSettings | None = None):
        self.settings = settings or FeedbackRerankSettings()
        self._pair_stats: dict[tuple[int, int], dict[str, int]] = {}
        self._global_total_samples = 0

    def load_historical_stats(self) -> None:
        """Fetch and aggregate approval rates for (host_scope, destination_scope) pairs."""
        from apps.suggestions.models import Suggestion

        # We only care about explicit human reviews: approved or rejected
        qs = (
            Suggestion.objects.filter(status__in=["approved", "rejected", "applied", "verified"])
            .values("host__scope_id", "destination__scope_id")
            .annotate(
                total=Count("suggestion_id"),
                successes=Count(
                    "suggestion_id", 
                    filter=Q(status__in=["approved", "applied", "verified"])
                ),
            )
        )

        self._pair_stats = {}
        self._global_total_samples = 0
        
        for row in qs:
            pair = (row["host__scope_id"], row["destination__scope_id"])
            self._pair_stats[pair] = {
                "total": row["total"],
                "successes": row["successes"],
            }
            self._global_total_samples += row["total"]

    def calculate_rerank_factor(
        self, 
        host_scope_id: int, 
        destination_scope_id: int
    ) -> tuple[float, dict[str, Any]]:
        """Compute the Explore/Exploit multiplier for a candidate pair."""
        if not self.settings.enabled:
            return 1.0, {"status": "disabled"}

        pair = (host_scope_id, destination_scope_id)
        stats = self._pair_stats.get(pair, {"total": 0, "successes": 0})
        
        n_total = stats["total"]
        n_success = stats["successes"]

        # 1. Exploit: Bayesian-Smoothed Acceptance Rate
        # mu = (success + alpha) / (total + alpha + beta)
        # Guard against zero denominator if priors are misconfigured.
        exploit_denom = n_total + self.settings.alpha_prior + self.settings.beta_prior
        score_exploit = (n_success + self.settings.alpha_prior) / max(exploit_denom, 1e-9)

        # 2. Explore: UCB1 Confidence Bound
        # Boost = k * sqrt(ln(N_global) / (n_pair + 1))
        # We use a small epsilon in ln to avoid log(0)
        n_global = max(1, self._global_total_samples)
        score_explore = self.settings.exploration_rate * math.sqrt(
            math.log(n_global + 1.0) / (n_total + 1.0)
        )

        # 3. Combined rerank factor
        # Initial score is multiplied by (1.0 + weight * (exploit + explore - 0.5))
        # 0.5 is subtracted because a neutral explore/exploit score is 0.5 (alpha=1, beta=1, total=0)
        raw_modifier = (score_exploit + score_explore) - 0.5
        factor = 1.0 + (self.settings.ranking_weight * raw_modifier)
        
        # Clamp factor to avoid excessive swings (e.g. 0.5x to 2.0x)
        factor = max(0.5, min(2.0, factor))

        diagnostics = {
            "n_pair": n_total,
            "n_success": n_success,
            "n_global": n_global,
            "score_exploit": round(score_exploit, 4),
            "score_explore": round(score_explore, 4),
            "raw_modifier": round(raw_modifier, 4),
            "final_factor": round(factor, 4),
        }

        return factor, diagnostics

    def rerank_candidates(
        self, 
        candidates: list[ScoredCandidate],
        host_scope_id_map: dict[int, int],  # host_content_id -> scope_id
        destination_scope_id_map: dict[int, int],  # dest_content_id -> scope_id
    ) -> list[ScoredCandidate]:
        """Apply the reranking factor to a list of candidates and update their scores."""
        from apps.pipeline.services.ranker import ScoredCandidate
        
        if not self.settings.enabled:
            return candidates

        if HAS_CPP_EXT:
            n_successes = []
            n_totals = []

            for c in candidates:
                host_scope = host_scope_id_map.get(c.host_content_id, 0)
                dest_scope = destination_scope_id_map.get(c.destination_content_id, 0)
                stats = self._pair_stats.get((host_scope, dest_scope), {"total": 0, "successes": 0})
                n_successes.append(int(stats["successes"]))
                n_totals.append(int(stats["total"]))

            factors = feedrerank.calculate_rerank_factors_batch(
                np.asarray(n_successes, dtype=np.int32),
                np.asarray(n_totals, dtype=np.int32),
                max(1, self._global_total_samples),
                float(self.settings.alpha_prior),
                float(self.settings.beta_prior),
                float(self.settings.ranking_weight),
                float(self.settings.exploration_rate),
            )

            from dataclasses import replace

            reranked = []
            for c, factor, n_success, n_total in zip(
                candidates,
                factors,
                n_successes,
                n_totals,
                strict=True,
            ):
                n_global = max(1, self._global_total_samples)
                score_exploit = (n_success + self.settings.alpha_prior) / (
                    n_total + self.settings.alpha_prior + self.settings.beta_prior
                )
                score_explore = self.settings.exploration_rate * math.sqrt(
                    math.log(n_global + 1.0) / (n_total + 1.0)
                )
                raw_modifier = (score_exploit + score_explore) - 0.5
                diags = {
                    "n_pair": n_total,
                    "n_success": n_success,
                    "n_global": n_global,
                    "score_exploit": round(score_exploit, 4),
                    "score_explore": round(score_explore, 4),
                    "raw_modifier": round(raw_modifier, 4),
                    "final_factor": round(float(factor), 4),
                }
                updated = replace(
                    c,
                    score_final=c.score_final * float(factor),
                    score_explore_exploit=round(float(factor), 4),
                    explore_exploit_diagnostics=diags,
                )
                reranked.append(updated)
            return reranked

        reranked = []
        for c in candidates:
            host_scope = host_scope_id_map.get(c.host_content_id, 0)
            dest_scope = destination_scope_id_map.get(c.destination_content_id, 0)
            
            factor, diags = self.calculate_rerank_factor(host_scope, dest_scope)
            
            new_score = c.score_final * factor
            
            # Create a new ScoredCandidate with the updated score
            # Note: ScoredCandidate is immutable (frozen=True)
            from dataclasses import replace
            updated = replace(
                c,
                score_final=new_score,
                score_explore_exploit=round(factor, 4),
                explore_exploit_diagnostics=diags
            )
            reranked.append(updated)
            
        return reranked
