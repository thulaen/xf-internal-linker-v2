"""Champion decisions for embedding-provider bake-offs."""

from __future__ import annotations

import itertools
import random
from dataclasses import dataclass
from typing import Mapping, Sequence

_P_VALUE_ALPHA = 0.05
_BAN_AFTER_LOSSES = 2
_MAX_EXACT_PAIRS = 16
_MAX_SIGN_SAMPLES = 4096
_SIGN_SAMPLE_SEED = 42


@dataclass(frozen=True, slots=True)
class ProviderScore:
    """One provider's aggregate and per-query quality scores."""

    provider: str
    ndcg_at_10: float
    query_scores: Sequence[float]


@dataclass(frozen=True, slots=True)
class ProviderVerdict:
    """Operator-visible result of comparing one provider to the champion."""

    provider: str
    compared_to: str
    verdict: str
    p_value: float
    loss_count: int
    is_banned: bool
    explanation: str


def paired_permutation_p_value(
    challenger_scores: Sequence[float],
    champion_scores: Sequence[float],
) -> float:
    """Return a two-sided paired randomisation p-value.

    Time complexity is O(N * S), where S is either every sign assignment for
    small samples or the capped deterministic sample count. Space is O(N).
    Python is acceptable here because this runs once per bake-off, not per
    suggestion candidate.
    """
    diffs = _paired_differences(challenger_scores, champion_scores)
    if not diffs:
        return 1.0
    observed = abs(sum(diffs) / len(diffs))
    if observed == 0:
        return 1.0
    extreme, total = _count_extreme_assignments(diffs, observed)
    return min(1.0, extreme / total if total else 1.0)


def decide_provider_verdicts(
    scores: Sequence[ProviderScore],
    *,
    champion_provider: str,
    existing_loss_counts: Mapping[str, int] | None = None,
) -> dict[str, ProviderVerdict]:
    """Compare every provider to the current champion and return verdicts."""
    score_by_provider = {row.provider: row for row in scores}
    champion = score_by_provider.get(champion_provider) or _best_score(scores)
    if champion is None:
        return {}
    losses = dict(existing_loss_counts or {})
    return {
        row.provider: _verdict_for_row(row, champion, losses.get(row.provider, 0))
        for row in scores
    }


def _paired_differences(
    challenger_scores: Sequence[float],
    champion_scores: Sequence[float],
) -> list[float]:
    return [
        float(challenger) - float(champion)
        for challenger, champion in zip(challenger_scores, champion_scores)
    ]


def _count_extreme_assignments(diffs: Sequence[float], observed: float) -> tuple[int, int]:
    total = 0
    extreme = 0
    for signs in _sign_assignments(len(diffs)):
        total += 1
        signed_mean = abs(sum(diff * sign for diff, sign in zip(diffs, signs)) / len(diffs))
        if signed_mean >= observed:
            extreme += 1
    return extreme, total


def _sign_assignments(count: int):
    if count <= _MAX_EXACT_PAIRS:
        yield from itertools.product((-1, 1), repeat=count)
        return
    # Deterministic statistical sampling; this is not used for security.
    rng = random.Random(_SIGN_SAMPLE_SEED)  # nosec B311
    for _ in range(_MAX_SIGN_SAMPLES):
        yield tuple(rng.choice((-1, 1)) for _ in range(count))


def _best_score(scores: Sequence[ProviderScore]) -> ProviderScore | None:
    if not scores:
        return None
    return max(scores, key=lambda row: row.ndcg_at_10)


def _verdict_for_row(
    row: ProviderScore,
    champion: ProviderScore,
    previous_losses: int,
) -> ProviderVerdict:
    if row.provider == champion.provider:
        return ProviderVerdict(
            row.provider,
            champion.provider,
            "champion",
            0.0,
            0,
            False,
            "This provider is the current champion.",
        )
    p_value = paired_permutation_p_value(row.query_scores, champion.query_scores)
    significant = p_value <= _P_VALUE_ALPHA
    beats_champion = row.ndcg_at_10 > champion.ndcg_at_10
    if significant and beats_champion:
        return _promote_verdict(row, champion, p_value)
    if significant:
        return _loss_verdict(row, champion, p_value, previous_losses)
    return _inconclusive_verdict(row, champion, p_value, previous_losses)


def _promote_verdict(
    row: ProviderScore,
    champion: ProviderScore,
    p_value: float,
) -> ProviderVerdict:
    return ProviderVerdict(
        row.provider,
        champion.provider,
        "promote",
        p_value,
        0,
        False,
        "This provider beat the current champion with a significant paired test.",
    )


def _loss_verdict(
    row: ProviderScore,
    champion: ProviderScore,
    p_value: float,
    previous_losses: int,
) -> ProviderVerdict:
    loss_count = previous_losses + 1
    return ProviderVerdict(
        row.provider,
        champion.provider,
        "loss",
        p_value,
        loss_count,
        loss_count >= _BAN_AFTER_LOSSES,
        "This provider lost to the champion with a significant paired test.",
    )


def _inconclusive_verdict(
    row: ProviderScore,
    champion: ProviderScore,
    p_value: float,
    previous_losses: int,
) -> ProviderVerdict:
    return ProviderVerdict(
        row.provider,
        champion.provider,
        "not_significant",
        p_value,
        previous_losses,
        previous_losses >= _BAN_AFTER_LOSSES,
        "The measured difference was not strong enough to switch providers.",
    )


__all__ = [
    "ProviderScore",
    "ProviderVerdict",
    "decide_provider_verdicts",
    "paired_permutation_p_value",
]
