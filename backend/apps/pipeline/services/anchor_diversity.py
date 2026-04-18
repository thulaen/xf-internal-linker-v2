"""FR-045 anchor diversity and exact-match reuse guard."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
import re
from typing import Iterable, Mapping, TypeAlias

ContentKey: TypeAlias = tuple[int, str]

ACTIVE_SUGGESTION_STATUSES = ("pending", "approved", "applied", "verified")
_NON_WORD_EDGE_RE = re.compile(r"^[^\w]+|[^\w]+$")
_WHITESPACE_RE = re.compile(r"\s+")


@dataclass(frozen=True, slots=True)
class AnchorDiversitySettings:
    enabled: bool = True
    ranking_weight: float = 0.03
    min_history_count: int = 3
    max_exact_match_share: float = 0.40
    max_exact_match_count: int = 3
    hard_cap_enabled: bool = False
    algorithm_version: str = "fr045-v1"


@dataclass(frozen=True, slots=True)
class AnchorHistory:
    active_anchor_count: int
    exact_match_counts: Mapping[str, int]


@dataclass(frozen=True, slots=True)
class AnchorDiversityEvaluation:
    score_anchor_diversity: float
    score_component: float
    repeated_anchor: bool
    blocked: bool
    diagnostics: dict[str, object]


def normalize_anchor_text(raw: str) -> str:
    """Normalize anchor text for exact-surface reuse checks."""
    lowered = _WHITESPACE_RE.sub(" ", (raw or "").strip().lower())
    cleaned = _NON_WORD_EDGE_RE.sub("", lowered).strip()
    return cleaned


def build_anchor_history(
    rows: Iterable[tuple[ContentKey, str]],
) -> dict[ContentKey, AnchorHistory]:
    """Return active normalized-anchor counts grouped by destination."""
    counters: dict[ContentKey, Counter[str]] = defaultdict(Counter)
    totals: Counter[ContentKey] = Counter()

    for destination_key, raw_anchor in rows:
        normalized = normalize_anchor_text(raw_anchor)
        if not normalized:
            continue
        counters[destination_key][normalized] += 1
        totals[destination_key] += 1

    return {
        destination_key: AnchorHistory(
            active_anchor_count=int(totals[destination_key]),
            exact_match_counts=dict(counter),
        )
        for destination_key, counter in counters.items()
    }


def evaluate_anchor_diversity(
    *,
    destination_key: ContentKey,
    candidate_anchor_text: str,
    history_by_destination: Mapping[ContentKey, AnchorHistory],
    settings: AnchorDiversitySettings,
) -> AnchorDiversityEvaluation:
    """Evaluate exact-match anchor concentration for one destination."""
    normalized = normalize_anchor_text(candidate_anchor_text)
    history = history_by_destination.get(
        destination_key,
        AnchorHistory(active_anchor_count=0, exact_match_counts={}),
    )
    exact_match_count_before = int(history.exact_match_counts.get(normalized, 0))
    repeated_anchor = bool(normalized and exact_match_count_before > 0)

    diagnostics: dict[str, object] = {
        "normalized_anchor": normalized,
        "active_anchor_count": int(history.active_anchor_count),
        "exact_match_count_before": exact_match_count_before,
        "projected_exact_match_count": exact_match_count_before,
        "projected_exact_share": 0.0,
        "max_exact_match_share": settings.max_exact_match_share,
        "max_exact_match_count": settings.max_exact_match_count,
        "share_overflow": 0.0,
        "count_overflow_norm": 0.0,
        "spam_risk": 0.0,
        "score_anchor_diversity": 0.5,
        "hard_cap_enabled": settings.hard_cap_enabled,
        "would_block": False,
        "active_statuses_considered": list(ACTIVE_SUGGESTION_STATUSES),
        "algorithm_version": settings.algorithm_version,
    }

    if not settings.enabled:
        diagnostics["anchor_diversity_state"] = "disabled"
        return AnchorDiversityEvaluation(
            score_anchor_diversity=0.5,
            score_component=0.0,
            repeated_anchor=repeated_anchor,
            blocked=False,
            diagnostics=diagnostics,
        )

    if not normalized:
        diagnostics["anchor_diversity_state"] = "neutral_no_anchor"
        return AnchorDiversityEvaluation(
            score_anchor_diversity=0.5,
            score_component=0.0,
            repeated_anchor=False,
            blocked=False,
            diagnostics=diagnostics,
        )

    if history.active_anchor_count < settings.min_history_count:
        diagnostics["anchor_diversity_state"] = "neutral_no_history"
        return AnchorDiversityEvaluation(
            score_anchor_diversity=0.5,
            score_component=0.0,
            repeated_anchor=repeated_anchor,
            blocked=False,
            diagnostics=diagnostics,
        )

    projected_exact_match_count = exact_match_count_before + 1
    projected_exact_share = projected_exact_match_count / max(
        history.active_anchor_count + 1,
        1,
    )
    share_overflow = max(
        0.0,
        projected_exact_share - settings.max_exact_match_share,
    ) / max(1.0 - settings.max_exact_match_share, 1e-9)
    count_overflow = max(
        0,
        projected_exact_match_count - settings.max_exact_match_count,
    )
    count_overflow_norm = min(
        1.0,
        count_overflow / max(settings.max_exact_match_count, 1),
    )
    spam_risk = min(1.0, 0.8 * share_overflow + 0.2 * count_overflow_norm)
    # FR-045 spec: neutral 0.5, lower means over-concentrated.
    score_anchor_diversity = 0.5 - 0.5 * spam_risk
    score_component = min(0.0, 2.0 * (score_anchor_diversity - 0.5))
    blocked = settings.hard_cap_enabled and (
        projected_exact_match_count > settings.max_exact_match_count
    )

    if blocked:
        state = "blocked_exact_count"
    elif count_overflow > 0:
        state = "penalized_exact_count"
    elif share_overflow > 0:
        state = "penalized_exact_share"
    else:
        state = "neutral_below_threshold"

    diagnostics.update(
        anchor_diversity_state=state,
        projected_exact_match_count=projected_exact_match_count,
        projected_exact_share=round(projected_exact_share, 6),
        share_overflow=round(share_overflow, 6),
        count_overflow_norm=round(count_overflow_norm, 6),
        spam_risk=round(spam_risk, 6),
        score_anchor_diversity=round(score_anchor_diversity, 6),
        would_block=blocked,
    )
    return AnchorDiversityEvaluation(
        score_anchor_diversity=score_anchor_diversity,
        score_component=score_component,
        repeated_anchor=repeated_anchor,
        blocked=blocked,
        diagnostics=diagnostics,
    )
