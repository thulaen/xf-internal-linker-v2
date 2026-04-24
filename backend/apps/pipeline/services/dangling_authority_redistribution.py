"""FR-099 Dangling Authority Redistribution Bonus (DARB).

Rewards candidates whose *host* post has high content-value authority but
few outbound internal links — the classic "dangling-node hoarder" pattern.
Boosting suggestions from these hosts encourages link equity to flow
outward from dangling hoarders into the rest of the site.

Source: Page, Brin, Motwani, Winograd (1999). "The PageRank Citation
Ranking: Bringing Order to the Web." Stanford InfoLab Publication 1999-66
§2.5 "Dangling Links" + §3.2 eq. 1.

This module is the ranker-layer *per-pair* signal. It does NOT modify the
PageRank matrix — FR-006 handles dangling-mass redistribution inside the
iteration. DARB uses the same mathematical intuition (inverse-out-degree
times authority) but applies it as a per-candidate score component.

Full spec: docs/specs/fr099-dangling-authority-redistribution-bonus.md
Gates applied: docs/RANKING-GATES.md Gate A (implementation).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, TypeAlias

ContentKey: TypeAlias = tuple[int, str]


@dataclass(frozen=True, slots=True)
class DARBSettings:
    """FR-099 ranking-signal settings. Defaults mirror recommended_weights.py."""

    enabled: bool = True
    ranking_weight: float = 0.04
    # Hosts with ≥ this many outbound links are considered non-dangling.
    # Baseline: Broder et al. 2000 Table 1 median out-degree ~8 — we use 5
    # (below median) to stay conservative.
    out_degree_saturation: int = 5
    # Hosts with content_value_score below this are not boosted.
    # 0.5 is the neutral midpoint per ContentItem.content_value_score help text.
    min_host_value: float = 0.5


@dataclass(frozen=True, slots=True)
class DARBEvaluation:
    """Per-pair DARB result. score_component is the value fed to the ranker."""

    score_component: float
    diagnostics: dict[str, Any] = field(default_factory=dict)


def evaluate_darb(
    *,
    host_key: ContentKey,
    host_content_value: float | None,
    existing_outgoing_counts: Mapping[ContentKey, int] | None,
    settings: DARBSettings,
) -> DARBEvaluation:
    """Compute the FR-099 DARB score for one candidate.

    Args:
        host_key: the host content item's key (the page adding the outbound link).
        host_content_value: ContentItem.content_value_score for the host, in [0, 1].
            None → cold start → neutral fallback.
        existing_outgoing_counts: dict of host_key → outbound internal-link count,
            precomputed once per pipeline run in pipeline_data.py.
        settings: DARBSettings with enabled flag, weight, thresholds.

    Returns:
        DARBEvaluation with score_component ≥ 0 (never negative) and diagnostics.
    """
    if not settings.enabled:
        return DARBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "disabled",
                "path": "python",
            },
        )

    if host_content_value is None or host_content_value != host_content_value:
        # NaN check via self-inequality. Same treatment as None.
        return DARBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "missing_host_value",
                "path": "python",
            },
        )

    # Clamp host_content_value to [0, 1] defensively.
    host_value = max(0.0, min(1.0, float(host_content_value)))

    if host_value < settings.min_host_value:
        return DARBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "below_neutral_host_value",
                "raw_host_value": host_value,
                "min_host_value_threshold": settings.min_host_value,
                "path": "python",
            },
        )

    if existing_outgoing_counts is None:
        return DARBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "missing_out_degree",
                "path": "python",
            },
        )

    host_out_degree = int(existing_outgoing_counts.get(host_key, 0))

    if host_out_degree >= settings.out_degree_saturation:
        return DARBEvaluation(
            score_component=0.0,
            diagnostics={
                "fallback_triggered": True,
                "diagnostic": "saturated_host",
                "raw_host_value": host_value,
                "raw_host_out_degree": host_out_degree,
                "saturation_threshold": settings.out_degree_saturation,
                "path": "python",
            },
        )

    # Source: Page et al. 1999 §3.2 eq. 1 — authority divided by out-degree
    # is the PageRank per-edge juice-per-edge term. Here we use it as a per-
    # pair ranker signal with content_value_score (composite) as authority.
    darb_raw = host_value / (1.0 + host_out_degree)
    # Clamp to [0, 1] — guaranteed by construction since 0 ≤ host_value ≤ 1
    # and out_degree ≥ 0.
    score_component = max(0.0, min(1.0, darb_raw))

    return DARBEvaluation(
        score_component=score_component,
        diagnostics={
            "fallback_triggered": False,
            "diagnostic": "ok",
            "raw_host_value": host_value,
            "raw_host_out_degree": host_out_degree,
            "saturation_threshold": settings.out_degree_saturation,
            "min_host_value_threshold": settings.min_host_value,
            "path": "python",
        },
    )
