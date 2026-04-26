"""Producer + read API for pick #35 Elo destination ratings.

Pick #35 ranks destinations by their Elo rating — a number that
captures "how often does this destination win when the operator
chooses between it and another candidate". The math lives in
:mod:`apps.pipeline.services.elo_rating`. This module is the
producer side: it derives pairwise outcomes from
``Suggestion.status`` history, runs the Elo update batch, and
persists per-destination ratings to ``ContentItem.elo_rating``.

Pair derivation (no Impression-tracking dependency)
---------------------------------------------------
Two reviewed Suggestions sharing the same ``host_sentence_id``
effectively competed for the same insertion slot — the operator
was choosing between them. We synthesise a :class:`PairwiseOutcome`
per such overlap:

- both **approved/applied** → draw (0.5)
- A **approved/applied**, B **rejected/declined/superseded** → A wins (1.0)
- both **rejected** → no signal, skip (no information about ordering)

This is coarser than impression-level pairwise data but uses inputs
that already exist (no new model, no UI hook required). When an
``Impression`` model lands later, the producer can switch to that
without changing the storage / consumer interface — both still
produce :class:`PairwiseOutcome` rows.

Read API (consumer-facing)
--------------------------
:func:`load_rating(content_key)` returns the persisted rating with
``DEFAULT_INITIAL_RATING`` (1500) as the cold-start fallback. The
ranker reads this directly — no snapshot loader pattern, since
``ContentItem`` is already in scope at suggestion-write time and
the rating travels with the row.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable

from .elo_rating import (
    DEFAULT_INITIAL_RATING,
    DEFAULT_K_FACTOR,
    DEFAULT_SCALE,
    EloState,
    PairwiseOutcome,
    run_batch,
)

logger = logging.getLogger(__name__)


#: Suggestion statuses that count as "operator approved" — A wins.
_POSITIVE_STATUSES: frozenset[str] = frozenset({"approved", "applied", "verified"})

#: Suggestion statuses that count as "operator rejected" — A loses.
_NEGATIVE_STATUSES: frozenset[str] = frozenset(
    {"rejected", "declined", "dismissed", "superseded"}
)


@dataclass(frozen=True)
class EloRefreshResult:
    """Audit trail for the scheduled-job UI."""

    pairs_processed: int
    destinations_rated: int
    skipped_no_signal: int


def derive_pairs_from_suggestion_history(
    *,
    days_lookback: int = 90,
) -> Iterable[PairwiseOutcome]:
    """Yield :class:`PairwiseOutcome` rows from operator-reviewed Suggestions.

    Looks back ``days_lookback`` days. Two Suggestions sharing the
    same ``host_sentence_id`` are treated as a head-to-head pair.

    Cold-start safe: returns an empty iterable when no reviewed
    Suggestions exist yet (fresh install, or before the review queue
    has accumulated history).
    """
    from datetime import timedelta

    from django.db.models import Q
    from django.utils import timezone

    from apps.suggestions.models import Suggestion

    cutoff = timezone.now() - timedelta(days=days_lookback)
    reviewed_q = Q(status__in=list(_POSITIVE_STATUSES | _NEGATIVE_STATUSES))
    rows = list(
        Suggestion.objects.filter(reviewed_q, updated_at__gte=cutoff).values_list(
            "host_sentence_id", "destination_id", "destination__content_type", "status"
        )
    )

    # Bucket reviewed suggestions by host_sentence; pairs come from
    # within-bucket cross products. Pre-build the buckets so we don't
    # do a quadratic scan over all rows for every pairing decision.
    buckets: dict[int, list[tuple[int, str, str]]] = {}
    for host_sid, dest_id, dest_type, status in rows:
        if host_sid is None:
            continue
        buckets.setdefault(host_sid, []).append((dest_id, dest_type, status))

    for entries in buckets.values():
        # Skip degenerate buckets (only one suggestion → no pair).
        if len(entries) < 2:
            continue
        for i in range(len(entries)):
            for j in range(i + 1, len(entries)):
                a_id, a_type, a_status = entries[i]
                b_id, b_type, b_status = entries[j]
                a_pos = a_status in _POSITIVE_STATUSES
                b_pos = b_status in _POSITIVE_STATUSES
                a_neg = a_status in _NEGATIVE_STATUSES
                b_neg = b_status in _NEGATIVE_STATUSES
                if a_pos and b_pos:
                    score_a = 0.5  # both accepted — draw
                elif a_pos and b_neg:
                    score_a = 1.0  # A beat B
                elif a_neg and b_pos:
                    score_a = 0.0  # B beat A
                else:
                    # both rejected → no ordering information; skip.
                    continue
                yield PairwiseOutcome(
                    item_a=(a_id, a_type),
                    item_b=(b_id, b_type),
                    score_a=score_a,
                )


def fit_and_persist_from_history(
    *,
    days_lookback: int = 90,
    k_factor: float = DEFAULT_K_FACTOR,
    scale: float = DEFAULT_SCALE,
) -> EloRefreshResult:
    """Run a full Elo refresh from review-queue history → ContentItem.

    Builds an :class:`EloState` from the persisted ratings, applies
    every derived pair, and writes the new ratings back. Call this
    from the scheduled job (``elo_rating_refresh``).

    Cold-start safe: zero pairs → zero updates → existing ratings
    untouched (which means the global initial rating, 1500, stays
    on every row).
    """
    from apps.content.models import ContentItem

    pairs = list(derive_pairs_from_suggestion_history(days_lookback=days_lookback))
    if not pairs:
        return EloRefreshResult(
            pairs_processed=0, destinations_rated=0, skipped_no_signal=0
        )

    # Pre-load the existing per-destination ratings so the batch
    # continues from the previous state instead of resetting to 1500
    # every run. ``ratings`` is keyed by ``(pk, content_type)`` to
    # match the Elo helper's signature.
    state = EloState()
    existing_rows = ContentItem.objects.filter(is_deleted=False).values_list(
        "pk", "content_type", "elo_rating"
    )
    for pk, content_type, rating in existing_rows:
        if rating is not None and rating != 0.0:
            state.ratings[(pk, content_type)] = float(rating)

    # Track which ratings the refresh actually touched so we don't
    # rewrite untouched rows and so ``destinations_rated`` reports
    # the real count of changes — not the ambient ContentItem
    # population.
    modified_keys: set = set()
    skipped = 0
    for outcome in pairs:
        try:
            run_batch(
                [outcome],
                initial_state=state,
                k_factor=k_factor,
                scale=scale,
                initial_rating=DEFAULT_INITIAL_RATING,
            )
            modified_keys.add(outcome.item_a)
            modified_keys.add(outcome.item_b)
        except Exception:
            # A single bad outcome (e.g. score_a out of [0,1]) must
            # not crash the whole refresh. Log + skip.
            logger.exception(
                "elo_rating: skipping outcome %s due to update failure", outcome
            )
            skipped += 1

    if not modified_keys:
        return EloRefreshResult(
            pairs_processed=len(pairs),
            destinations_rated=0,
            skipped_no_signal=skipped,
        )

    # Persist only the ratings that changed, grouped by content_type
    # so we can do per-type bulk_update with the pk filter — avoids
    # loading every ContentItem at once.
    by_type: dict[str, list[tuple[int, float]]] = {}
    for key in modified_keys:
        pk, content_type = key
        rating = state.ratings.get(key)
        if rating is None:
            continue
        by_type.setdefault(content_type, []).append((pk, float(rating)))

    rated = 0
    for content_type, items in by_type.items():
        pk_to_rating = {pk: rating for pk, rating in items}
        rows = list(
            ContentItem.objects.filter(
                pk__in=list(pk_to_rating.keys()), content_type=content_type
            )
        )
        for row in rows:
            row.elo_rating = pk_to_rating[row.pk]
        ContentItem.objects.bulk_update(rows, ["elo_rating"])
        rated += len(rows)

    return EloRefreshResult(
        pairs_processed=len(pairs),
        destinations_rated=rated,
        skipped_no_signal=skipped,
    )
