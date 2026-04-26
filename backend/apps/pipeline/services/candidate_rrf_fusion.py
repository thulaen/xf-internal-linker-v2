"""Candidate-list fusion via Reciprocal Rank Fusion — pick #31 wiring.

W3d ships an opt-in fusion service over multiple candidate-retrieval
sources. The existing Stage 1 in :mod:`apps.pipeline.services.pipeline_stages`
runs a single FAISS-semantic top-K search per destination. RRF lets
callers combine that with rank-based signals from the graph-signal
store (HITS authority, Personalized PageRank, TrustRank) so a
candidate that ranks well on multiple axes outranks one that's only
strong on cosine similarity.

Why this is opt-in rather than a Stage-1 replacement:

- The current scoring contract is point-wise (per-(destination,
  host_sentence) composite scores). RRF is rank-based — fundamentally
  a different aggregation. Wiring it as the default candidate
  generator would require synchronising every downstream consumer of
  ``sentence_matches``.
- Shipping the fusion as a stand-alone helper lets callers (a future
  reranker, a dashboard "best matches by HITS authority" view, the
  W4 Explain panel) opt into RRF without breaking the production
  ranker.

Callers hand in a dict ``{ranker_name: ranked_doc_ids}``. The helper
delegates to :func:`apps.pipeline.services.reciprocal_rank_fusion.fuse`
(pick #31, k=60 default) and additionally injects graph-signal
rankings when the caller asks for them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Hashable, Iterable, Mapping, Sequence

from .graph_signal_store import (
    SIGNAL_HITS_AUTHORITY,
    SIGNAL_PPR,
    SIGNAL_TRUSTRANK,
    load_snapshot,
)
from .reciprocal_rank_fusion import DEFAULT_RRF_K, FusedItem, fuse

logger = logging.getLogger(__name__)


#: Default graph-signal rankers that get spliced into the fusion when
#: a caller passes ``include_graph_signals=True``. Operators can pass
#: their own subset to control which signals contribute.
DEFAULT_GRAPH_SIGNALS: tuple[str, ...] = (
    SIGNAL_HITS_AUTHORITY,
    SIGNAL_PPR,
    SIGNAL_TRUSTRANK,
)


@dataclass(frozen=True)
class FusionResult:
    """Output of :func:`fuse_candidates` — the fused order plus diagnostics."""

    fused: list[FusedItem]
    contributing_rankers: list[str]
    graph_signals_used: list[str]


def fuse_candidates(
    primary_rankings: Mapping[str, Sequence[Hashable]],
    *,
    include_graph_signals: bool = False,
    graph_signals: Iterable[str] = DEFAULT_GRAPH_SIGNALS,
    k: int = DEFAULT_RRF_K,
    top_n: int | None = None,
    candidate_universe: Iterable[Hashable] | None = None,
) -> FusionResult:
    """Fuse one or more ranked candidate lists into a single ordering.

    Parameters
    ----------
    primary_rankings
        ``{ranker_name: ordered_candidate_ids}``. Caller-supplied
        retrievers (e.g. ``{"semantic": [...], "bm25": [...]}``).
    include_graph_signals
        When ``True``, the function also injects ranked lists from
        the graph-signal store (HITS authority, PPR, TrustRank) so
        candidates with a strong graph footprint surface even when
        their lexical match is weak.
    graph_signals
        Override the default set of graph rankers to splice in.
    k
        RRF smoothing constant. 60 = pick-31 default.
    top_n
        Truncate the fused list. ``None`` = keep all candidates.
    candidate_universe
        When given, the graph-signal rankings are restricted to this
        universe so a global "top by HITS" doesn't drown out the
        retriever's own candidates. Typical caller passes its current
        candidate-pool IDs.

    Returns
    -------
    :class:`FusionResult` with the fused ordering and a list of the
    rankers that actually contributed (so dashboards can show "10
    candidates fused from 4 sources").
    """
    rankings: dict[str, Sequence[Hashable]] = dict(primary_rankings)
    contributing = list(primary_rankings.keys())
    used_signals: list[str] = []

    if include_graph_signals:
        universe_set = (
            {candidate for candidate in candidate_universe}
            if candidate_universe is not None
            else None
        )
        for signal_name in graph_signals:
            ranking = _ranking_from_graph_signal(signal_name, universe=universe_set)
            if ranking:
                rankings[f"graph:{signal_name}"] = ranking
                contributing.append(f"graph:{signal_name}")
                used_signals.append(signal_name)

    if not rankings:
        return FusionResult(fused=[], contributing_rankers=[], graph_signals_used=[])

    fused_items = fuse(rankings, k=k, top_n=top_n)
    return FusionResult(
        fused=fused_items,
        contributing_rankers=contributing,
        graph_signals_used=used_signals,
    )


# ── Internals ────────────────────────────────────────────────────


def _ranking_from_graph_signal(
    signal_name: str, *, universe: set[Hashable] | None = None
) -> list[Hashable] | None:
    """Return a ranked candidate list derived from the persisted graph-signal store.

    The store keys are ``"<pk>:<content_type>"`` strings. We translate
    them back to ``(pk, content_type)`` tuples so they line up with
    the ContentKey shape callers use elsewhere.
    """
    snap = load_snapshot(signal_name)
    if snap is None or not snap.scores:
        return None
    # Sort by descending score; ties broken by string lookup so the
    # order is deterministic across runs.
    pairs = sorted(snap.scores.items(), key=lambda pair: (-pair[1], pair[0]))
    ranked: list[Hashable] = []
    for token, _ in pairs:
        candidate = _token_to_key(token)
        if universe is not None and candidate not in universe:
            continue
        ranked.append(candidate)
    return ranked or None


def _token_to_key(token: str) -> Hashable:
    """Translate a persisted ``"<pk>:<content_type>"`` string back to a key.

    Matches the encoding used by
    :func:`apps.pipeline.services.graph_signal_store._key_to_token`.
    Falls back to the raw string when the colon-delimited shape isn't
    detected.
    """
    if ":" in token:
        head, _, tail = token.partition(":")
        try:
            return (int(head), tail)
        except ValueError:
            return token
    try:
        return int(token)
    except ValueError:
        return token
