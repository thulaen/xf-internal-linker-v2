"""FR-104 Host-Graph Topic Entropy Boost (HGTE).

Rewards candidates whose addition would increase the Shannon entropy of
the host's outbound-link silo distribution — i.e. links that diversify
the host's topical portfolio.

Source: Shannon, C. E. (1948). "A Mathematical Theory of Communication."
Bell System Technical Journal 27(3):379–423, DOI
10.1002/j.1538-7305.1948.tb01338.x. §6 eq. 4:
    H(X) = -Σ p_i · log(p_i)

Click-weighted variant not used here — equal-weighted frequency count is
the plug-in entropy estimator (Cover & Thomas 2006 §2.1 eq. 2.4).

Full spec: docs/specs/fr104-host-graph-topic-entropy-boost.md
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Mapping, TypeAlias

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class HGTESettings:
    enabled: bool = True
    ranking_weight: float = 0.04
    min_host_out_degree: int = 3


@dataclass(frozen=True, slots=True)
class HGTEEvaluation:
    score_component: float
    diagnostics: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class HostSiloDistributionCache:
    """Per-pipeline-run precompute for HGTE.

    - host_silo_counts: host_key -> {silo_id: count of outbound edges to that silo}
    - num_silos: total distinct silos in the corpus (bounds the entropy range)
    """

    host_silo_counts: dict[ContentKey, dict[int, int]]
    num_silos: int


def _shannon_entropy_bits(counts: Mapping[int, int]) -> float:
    """H(X) = -Σ p · log2(p). Returns 0.0 for empty or single-item distributions."""
    total = sum(counts.values())
    if total <= 0:
        return 0.0
    h = 0.0
    for c in counts.values():
        if c <= 0:
            continue
        p = c / total
        # Source: Shannon 1948 §6 eq. 4 — base-2 log for bits.
        h -= p * math.log2(p)
    return h


def evaluate_hgte(
    *,
    host_key: ContentKey,
    dest_silo_id: int | None,
    silo_cache: HostSiloDistributionCache | None,
    settings: HGTESettings,
) -> HGTEEvaluation:
    """Compute the entropy-delta bonus for adding host→dest.

    Returns a score in [0, 1] — 0 if adding the link decreases entropy or
    the setup is invalid; positive if entropy increases.
    """
    if not settings.enabled:
        return HGTEEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "disabled",
                "path": "python",
            },
        )

    if silo_cache is None:
        return HGTEEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "host_silo_map_missing",
                "path": "python",
            },
        )

    if dest_silo_id is None:
        return HGTEEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "dest_no_silo",
                "path": "python",
            },
        )

    counts_before = silo_cache.host_silo_counts.get(host_key)
    if not counts_before:
        # Host has no outbound silo data — can't compute entropy delta.
        return HGTEEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "host_silo_map_missing",
                "path": "python",
            },
        )

    host_out_degree = sum(counts_before.values())
    if host_out_degree < settings.min_host_out_degree:
        return HGTEEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "low_host_out_degree",
                "host_out_degree": host_out_degree,
                "min_required": settings.min_host_out_degree,
                "path": "python",
            },
        )

    h_before = _shannon_entropy_bits(counts_before)

    # Simulate adding the candidate link to dest's silo.
    counts_after = dict(counts_before)
    counts_after[dest_silo_id] = counts_after.get(dest_silo_id, 0) + 1
    h_after = _shannon_entropy_bits(counts_after)

    entropy_delta = h_after - h_before

    # Normalize by max possible entropy (uniform distribution over all silos).
    # Source: Shannon 1948 Theorem 2 — H_max = log2(N) for N equally-likely events.
    if silo_cache.num_silos <= 1:
        max_entropy = 1.0  # Avoid div by zero; degenerate single-silo case
    else:
        max_entropy = math.log2(silo_cache.num_silos)

    if entropy_delta <= 0.0:
        return HGTEEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "entropy_decreasing",
                "host_out_degree": host_out_degree,
                "host_silo_count_before": len(counts_before),
                "host_silo_count_after": len(counts_after),
                "entropy_before": round(h_before, 6),
                "entropy_after": round(h_after, 6),
                "entropy_delta": round(entropy_delta, 6),
                "max_entropy": round(max_entropy, 6),
                "path": "python",
            },
        )

    score_component = max(0.0, min(1.0, entropy_delta / max_entropy))

    return HGTEEvaluation(
        score_component=score_component,
        diagnostics={
            "fallback_triggered": False,
            "diagnostic": "ok",
            "host_out_degree": host_out_degree,
            "host_silo_count_before": len(counts_before),
            "host_silo_count_after": len(counts_after),
            "entropy_before": round(h_before, 6),
            "entropy_after": round(h_after, 6),
            "entropy_delta": round(entropy_delta, 6),
            "max_entropy": round(max_entropy, 6),
            "normalized_delta": round(score_component, 6),
            "path": "python",
        },
    )
