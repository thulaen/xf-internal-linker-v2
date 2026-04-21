"""FR-13 Feedback-Driven Explore/Exploit Reranker.

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
    exploration_rate: float = recommended_float(
        "explore_exploit.exploration_rate"
    )  # k factor in UCB1 sqrt(k * ln(N)/n)
    alpha_prior: float = 1.0  # Bayesian smoothing alpha (prior approved)
    beta_prior: float = 1.0  # Bayesian smoothing beta (prior rejected)


class FeedbackRerankService:
    """Learns from Suggestion status history to bias future rankings."""

    def __init__(self, settings: FeedbackRerankSettings | None = None):
        self.settings = settings or FeedbackRerankSettings()
        self._pair_stats: dict[tuple[int, int], dict[str, int]] = {}
        self._global_total_samples = 0

    def load_historical_stats(self) -> None:
        """Aggregate approval rates per (host_scope, destination_scope) pair.

        For each pair computes ``observation_confidence`` = reviews /
        presentations (falls back to generated-count when no presentation
        data exists). This is a per-pair linear confidence blend, NOT an
        inverse-propensity estimator — see the feedrerank audit Finding 2
        (resolved in April 2026) in REPORT-REGISTRY.md for the gap
        analysis. Joachims, Swaminathan & Schnabel (WSDM paper cited in
        the pybind11 module docstring) describes a rigorous per-event IPS
        estimator; kept as inspiration only.
        """
        from apps.suggestions.models import Suggestion, SuggestionPresentation

        # Count reviewed suggestions per pair (explicit human reviews only)
        reviewed_qs = (
            Suggestion.objects.filter(
                status__in=["approved", "rejected", "applied", "verified"]
            )
            .values("host__scope_id", "destination__scope_id")
            .annotate(
                total=Count("suggestion_id"),
                successes=Count(
                    "suggestion_id",
                    filter=Q(status__in=["approved", "applied", "verified"]),
                ),
            )
        )

        # Count presented suggestions per pair (exposure-based denominator)
        has_presentations = SuggestionPresentation.objects.exists()

        presented_map: dict[tuple[int, int], int] = {}
        if has_presentations:
            presented_qs = SuggestionPresentation.objects.values(
                "suggestion__host__scope_id",
                "suggestion__destination__scope_id",
            ).annotate(presented=Count("id", distinct=True))
            for row in presented_qs:
                pair = (
                    row["suggestion__host__scope_id"],
                    row["suggestion__destination__scope_id"],
                )
                presented_map[pair] = row["presented"]

        # Fallback: count ALL generated suggestions per pair
        generated_map: dict[tuple[int, int], int] = {}
        if not has_presentations:
            generated_qs = Suggestion.objects.values(
                "host__scope_id", "destination__scope_id"
            ).annotate(generated=Count("suggestion_id"))
            for row in generated_qs:
                pair = (row["host__scope_id"], row["destination__scope_id"])
                generated_map[pair] = row["generated"]

        self._pair_stats = {}
        self._global_total_samples = 0

        for row in reviewed_qs:
            pair = (row["host__scope_id"], row["destination__scope_id"])
            # Prefer presented count; fall back to generated count
            n_exposure = presented_map.get(pair, generated_map.get(pair, row["total"]))
            observation_confidence = row["total"] / max(n_exposure, 1)
            self._pair_stats[pair] = {
                "total": row["total"],
                "successes": row["successes"],
                "presented": presented_map.get(pair, 0),
                "generated": generated_map.get(pair, 0),
                "observation_confidence": observation_confidence,
            }
            self._global_total_samples += row["total"]

    def calculate_rerank_factor(
        self, host_scope_id: int, destination_scope_id: int
    ) -> tuple[float, dict[str, Any]]:
        """Compute the Explore/Exploit multiplier for a candidate pair.

        Blends the pair's Bayesian-smoothed acceptance rate toward neutral
        0.5 based on ``observation_confidence`` = reviews / impressions.
        This is a per-pair linear confidence blend, NOT an inverse-propensity
        estimator (see the feedrerank audit Finding 2 in REPORT-REGISTRY.md).
        """
        if not self.settings.enabled:
            return 1.0, {"status": "disabled"}

        pair = (host_scope_id, destination_scope_id)
        stats = self._pair_stats.get(
            pair,
            {
                "total": 0,
                "successes": 0,
                "presented": 0,
                "generated": 0,
                "observation_confidence": 0.0,
            },
        )

        n_total = stats["total"]
        n_success = stats["successes"]
        oc = stats.get("observation_confidence", 0.0)

        # 1. Exploit: Bayesian-Smoothed Acceptance Rate blended toward 0.5
        # by observation_confidence. Linear confidence blend, NOT IPS
        # (see the feedrerank audit Finding 2 in REPORT-REGISTRY.md).
        exploit_denom = n_total + self.settings.alpha_prior + self.settings.beta_prior
        score_exploit_raw = (n_success + self.settings.alpha_prior) / max(
            exploit_denom, 1e-9
        )
        score_exploit = oc * score_exploit_raw + (1.0 - oc) * 0.5

        # 2. Explore: UCB1 Confidence Bound
        # Boost = k * sqrt(ln(N_global) / (n_pair + 1))
        n_global = max(1, self._global_total_samples)
        score_explore = self.settings.exploration_rate * math.sqrt(
            math.log(n_global + 1.0) / (n_total + 1.0)
        )

        # 3. Combined rerank factor. Subtract 0.5 because that is the
        # neutral explore/exploit baseline; clamp to [0.5, 2.0] swings.
        raw_modifier = (score_exploit + score_explore) - 0.5
        factor = 1.0 + (self.settings.ranking_weight * raw_modifier)
        factor = max(0.5, min(2.0, factor))

        diagnostics = {
            "n_pair": n_total,
            "n_success": n_success,
            "n_presented": stats.get("presented", 0),
            "n_generated": stats.get("generated", 0),
            "observation_confidence": round(oc, 4),
            "n_global": n_global,
            "score_exploit_raw": round(score_exploit_raw, 4),
            "score_exploit": round(score_exploit, 4),
            "score_explore": round(score_explore, 4),
            "raw_modifier": round(raw_modifier, 4),
            "final_factor": round(factor, 4),
        }

        return factor, diagnostics

    def _collect_pair_arrays(
        self,
        candidates: list[ScoredCandidate],
        host_scope_id_map: dict[int, int],
        destination_scope_id_map: dict[int, int],
    ) -> tuple[list[int], list[int], list[float]]:
        """Build per-candidate success / total / observation_confidence arrays
        from pair stats for the C++ batch reranker.
        """
        n_successes: list[int] = []
        n_totals: list[int] = []
        observation_confidences: list[float] = []
        for c in candidates:
            host_scope = host_scope_id_map.get(c.host_content_id, 0)
            dest_scope = destination_scope_id_map.get(c.destination_content_id, 0)
            stats = self._pair_stats.get(
                (host_scope, dest_scope), {"total": 0, "successes": 0}
            )
            n_successes.append(int(stats["successes"]))
            n_totals.append(int(stats["total"]))
            observation_confidences.append(
                float(stats.get("observation_confidence", 1.0))
            )
        return n_successes, n_totals, observation_confidences

    def _rerank_cpp_batch(
        self,
        candidates: list[ScoredCandidate],
        n_successes: list[int],
        n_totals: list[int],
        observation_confidences: list[float],
    ) -> list[ScoredCandidate]:
        """C++ accelerated batch reranking with per-candidate diagnostics."""
        from dataclasses import replace

        factors = feedrerank.calculate_rerank_factors_batch(
            np.asarray(n_successes, dtype=np.int32),
            np.asarray(n_totals, dtype=np.int32),
            np.asarray(observation_confidences, dtype=np.float64),
            max(1, self._global_total_samples),
            float(self.settings.alpha_prior),
            float(self.settings.beta_prior),
            float(self.settings.ranking_weight),
            float(self.settings.exploration_rate),
        )
        reranked = []
        for c, factor, n_success, n_total, oc in zip(
            candidates,
            factors,
            n_successes,
            n_totals,
            observation_confidences,
            strict=True,
        ):
            n_global = max(1, self._global_total_samples)
            # 1e-9 denominator guard mirrors calculate_rerank_factor (line 156).
            # Prevents Infinity/NaN in the diagnostics when an operator zeroes
            # both priors AND n_total is zero. Closes RPT-001 Finding 3.
            exploit_denom = (
                n_total + self.settings.alpha_prior + self.settings.beta_prior
            )
            score_exploit_raw = (n_success + self.settings.alpha_prior) / max(
                exploit_denom, 1e-9
            )
            # Linear observation_confidence blend toward neutral 0.5.
            # See RPT-001 Finding 2 — this is a per-pair confidence blend,
            # NOT an inverse-propensity estimator. Joachims, Swaminathan &
            # Schnabel 2017 (DOI 10.1145/3077136.3080756) describes the
            # rigorous per-event IPS alternative; kept as inspiration only.
            score_exploit = oc * score_exploit_raw + (1.0 - oc) * 0.5
            score_explore = self.settings.exploration_rate * math.sqrt(
                math.log(n_global + 1.0) / (n_total + 1.0)
            )
            raw_modifier = (score_exploit + score_explore) - 0.5
            diags = {
                "n_pair": n_total,
                "n_success": n_success,
                "n_global": n_global,
                "observation_confidence": round(oc, 4),
                "score_exploit_raw": round(score_exploit_raw, 4),
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

    def rerank_candidates(
        self,
        candidates: list[ScoredCandidate],
        host_scope_id_map: dict[int, int],
        destination_scope_id_map: dict[int, int],
    ) -> list[ScoredCandidate]:
        """Apply the reranking factor to a list of candidates and update their scores."""
        if not self.settings.enabled:
            return candidates

        if HAS_CPP_EXT:
            n_successes, n_totals, observation_confidences = self._collect_pair_arrays(
                candidates, host_scope_id_map, destination_scope_id_map
            )
            return self._rerank_cpp_batch(
                candidates, n_successes, n_totals, observation_confidences
            )

        from dataclasses import replace

        reranked = []
        for c in candidates:
            host_scope = host_scope_id_map.get(c.host_content_id, 0)
            dest_scope = destination_scope_id_map.get(c.destination_content_id, 0)
            factor, diags = self.calculate_rerank_factor(host_scope, dest_scope)
            updated = replace(
                c,
                score_final=c.score_final * factor,
                score_explore_exploit=round(factor, 4),
                explore_exploit_diagnostics=diags,
            )
            reranked.append(updated)
        return reranked
