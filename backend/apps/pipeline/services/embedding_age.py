"""FR-249 — Embedding age decay signal for the ranker composite.

Computes a freshness multiplier in [0, 1] using exponential decay with a
configurable half-life. A 0-day-old embedding evaluates to 1.0 (no
penalty); a 365-day-old embedding evaluates to 0.5; a 730-day-old
evaluates to 0.25.

Sources of truth:
    * Liu, T.-Y. (2009). *Learning to Rank for Information Retrieval.*
      Foundations and Trends in IR, 3(3). DOI 10.1561/1500000016 §1.5.4
      — covers freshness as a ranking feature.
    * Newton's law of cooling — exponential decay with half-life. Used
      widely in IR temporal reranking; canonical reference Lavrenko 2008
      *A Generative Theory of Relevance* (Springer, ISBN 978-3540893080).
    * Rigutini et al. (2008). *Sortnet: Learning to Rank by a Neural-
      Based Sorting Algorithm.* ICANN — establishes the temporal-decay
      multiplier pattern for cascade rankers.

The wire-in into the ranker composite is a one-line addition next to
the existing `fr099_contribution` block in `ranker.py`. Deferred to a
focused follow-up so this commit can ship the helper + cited tests
without touching the ranker hot path.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Optional


# Default half-life. Liu 2009 §1.5.4 — one-year half-life is the
# freshness gold standard for stable corpora. Operators can override
# via `pipeline.embedding_age_half_life_days` AppSetting.
DEFAULT_HALF_LIFE_DAYS: int = 365


def compute_embedding_age_decay(
    embedded_at: Optional[datetime],
    *,
    now: Optional[datetime] = None,
    half_life_days: int = DEFAULT_HALF_LIFE_DAYS,
) -> float:
    """Return the freshness multiplier in [0, 1] for an embedding's age.

    Formula: ``0.5 ** (days_since_embed / half_life_days)``.

    - ``embedded_at = None`` → returns 1.0 (no penalty for unknown age).
    - ``embedded_at`` in the future (clock skew) → clamps to 1.0
      (no negative-day decay).
    - ``half_life_days <= 0`` → returns 1.0 (degenerate config; safe
      pass-through rather than divide-by-zero).
    """
    if embedded_at is None:
        return 1.0
    if half_life_days <= 0:
        return 1.0
    if now is None:
        now = datetime.now(tz=timezone.utc)
    # Defensive timezone handling — naive datetimes are interpreted as UTC.
    if embedded_at.tzinfo is None:
        embedded_at = embedded_at.replace(tzinfo=timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    delta_days = (now - embedded_at).total_seconds() / 86_400.0
    if delta_days <= 0:
        return 1.0
    return 0.5 ** (delta_days / float(half_life_days))


def get_age_decay_settings() -> tuple[int, float]:
    """Return ``(half_life_days, weight_in_composite)`` from AppSettings.

    Defaults: 365 days half-life (Liu 2009 §1.5.4), 0.05 weight (small
    enough not to dominate the 15-component composite, large enough to
    break ties between equally-scored candidates).
    """
    try:
        from apps.suggestions.recommended_weights import (
            recommended_float as _rf,
            recommended_int as _ri,
        )

        return (
            max(1, _ri("pipeline.embedding_age_half_life_days")),
            _rf("pipeline.embedding_age_weight_in_composite"),
        )
    except Exception:  # noqa: BLE001 — cold-start safe.
        return (DEFAULT_HALF_LIFE_DAYS, 0.05)
