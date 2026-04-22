"""Elo rating — pairwise approve/reject → rating (Elo 1978).

Reference
---------
Elo, A. E. (1978). *The Rating of Chessplayers, Past and Present*.
Arco Publishing.

Goal
----
Turn a stream of pairwise comparisons ("operator approved suggestion
A over suggestion B") into a single rating per item that reflects
its relative quality over many matchups — even when each individual
pair contributes one bit of signal.

The two-line Elo recurrence::

    E_a = 1 / (1 + 10 ** ((R_b - R_a) / scale))
    R_a' = R_a + K * (S_a - E_a)

``E_a`` is the expected outcome for player A (between 0 and 1);
``S_a`` is the actual outcome (1 for win, 0.5 for draw, 0 for loss);
``K`` is the learning rate (Elo's chess convention = 32; adjust down
for high-volume streams to avoid oscillation).

Why not simple win-rate?
  Wins against strong opponents count more than wins against weak
  ones. Elo's exponential scoring captures that without any model
  of individual strengths — the ratings arise from the recurrence.

This module is pure arithmetic. Callers feed comparisons in, get
ratings out; a scheduled job fires it with reviewer-feedback data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Hashable, Iterable


#: Elo's chess convention; K = 32 for the first ~30 games, then
#: smaller. For the linker's low-volume editorial feedback, 32 keeps
#: ratings responsive; drop to 16 once an item has > 30 matches.
DEFAULT_K_FACTOR: float = 32.0

#: Elo's original paper uses 400 so that a 200-point gap means
#: roughly 75 % expected win rate.
DEFAULT_SCALE: float = 400.0

#: Initial rating for a previously-unseen item. 1500 is the USCF
#: convention and lines up with ChessBase's defaults.
DEFAULT_INITIAL_RATING: float = 1500.0


@dataclass(frozen=True)
class PairwiseOutcome:
    """One match between two items.

    ``score_a`` is the actual outcome from A's perspective: 1.0 for
    "A beat B", 0.5 for "draw", 0.0 for "B beat A". Callers mapping
    editorial feedback to this typically use:

    - accepted A over B → ``score_a = 1.0``
    - both accepted     → ``score_a = 0.5``
    - accepted B over A → ``score_a = 0.0``
    """

    item_a: Hashable
    item_b: Hashable
    score_a: float


@dataclass
class EloState:
    """Mutable rating state. Pass around a shared instance to batch updates."""

    ratings: dict[Hashable, float] = field(default_factory=dict)
    match_counts: dict[Hashable, int] = field(default_factory=dict)

    def get(
        self,
        item: Hashable,
        *,
        default: float = DEFAULT_INITIAL_RATING,
    ) -> float:
        """Return *item*'s rating (falling back to *default*)."""
        return self.ratings.get(item, default)


def expected_score(
    *,
    rating_a: float,
    rating_b: float,
    scale: float = DEFAULT_SCALE,
) -> float:
    """Return ``E_a`` — the probability A beats B under Elo's formula."""
    diff = rating_b - rating_a
    return 1.0 / (1.0 + pow(10.0, diff / scale))


def update(
    state: EloState,
    outcome: PairwiseOutcome,
    *,
    k_factor: float = DEFAULT_K_FACTOR,
    scale: float = DEFAULT_SCALE,
    initial_rating: float = DEFAULT_INITIAL_RATING,
) -> tuple[float, float]:
    """Apply *outcome* to *state*, returning the post-match ratings.

    Returns ``(new_rating_a, new_rating_b)``.

    Raises
    ------
    ValueError
        If ``score_a`` is not in ``[0, 1]``.
    """
    if not 0.0 <= outcome.score_a <= 1.0:
        raise ValueError("score_a must be in [0, 1]")

    ra = state.get(outcome.item_a, default=initial_rating)
    rb = state.get(outcome.item_b, default=initial_rating)
    ea = expected_score(rating_a=ra, rating_b=rb, scale=scale)
    eb = 1.0 - ea
    sa = outcome.score_a
    sb = 1.0 - sa

    new_ra = ra + k_factor * (sa - ea)
    new_rb = rb + k_factor * (sb - eb)
    state.ratings[outcome.item_a] = new_ra
    state.ratings[outcome.item_b] = new_rb
    state.match_counts[outcome.item_a] = state.match_counts.get(outcome.item_a, 0) + 1
    state.match_counts[outcome.item_b] = state.match_counts.get(outcome.item_b, 0) + 1
    return new_ra, new_rb


def run_batch(
    outcomes: Iterable[PairwiseOutcome],
    *,
    initial_state: EloState | None = None,
    k_factor: float = DEFAULT_K_FACTOR,
    scale: float = DEFAULT_SCALE,
    initial_rating: float = DEFAULT_INITIAL_RATING,
) -> EloState:
    """Apply every outcome in order and return the final state.

    Pass ``initial_state`` to continue a previous batch (the
    scheduled Elo job persists the state between runs).
    """
    state = initial_state or EloState()
    for outcome in outcomes:
        update(
            state,
            outcome,
            k_factor=k_factor,
            scale=scale,
            initial_rating=initial_rating,
        )
    return state
