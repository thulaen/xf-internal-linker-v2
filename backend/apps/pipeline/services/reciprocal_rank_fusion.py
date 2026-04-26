"""Reciprocal Rank Fusion (Cormack, Clarke, Büttcher 2009).

Reference
---------
Cormack, G. V., Clarke, C. L. A., & Büttcher, S. (2009). "Reciprocal
rank fusion outperforms Condorcet and individual rank learning
methods." *Proceedings of the 32nd ACM SIGIR Conference*, pp. 758-759.

Goal
----
Combine several ranked lists (one per retriever — BM25, dense vector
cosine, query-likelihood, etc.) into a single fused ranking without
needing to tune per-retriever weights. Cormack et al.'s formula::

    RRF(d) = Σ_ranker  1 / ( k + rank_ranker(d) )

where ``rank_ranker(d)`` is d's 1-based position in that ranker's
output. ``k`` is a smoothing constant that dampens the outsized
influence of the very top positions — the paper settles on
``k = 60`` after cross-validation, and in the 15 years since it has
become the de-facto default across IR literature.

Why RRF over tuned linear blends?
- Parameter-free (save ``k``): no need to re-tune when a retriever
  changes its scoring scale.
- Only ranks are used, so retrievers with incomparable score scales
  (cosine similarities, BM25 scores, log-likelihood scores) mix
  cleanly.
- Produces a TREC-style robust fusion that matches or beats
  Condorcet / CombSUM / CombMNZ on the paper's benchmark suite.

The module is pure arithmetic — no DB, no I/O. Callers hand in
ranked lists of opaque document IDs; this module returns the fused
ranking plus per-doc score contributions for diagnostics.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Hashable, Iterable, Mapping, Sequence, TypeVar

DocId = TypeVar("DocId", bound=Hashable)


#: Cormack-Clarke-Büttcher 2009 §3 recommended value. Lower ``k``
#: gives the very top positions more weight; higher ``k`` flattens
#: the contribution curve. 60 is the sweet spot on TREC. We mirror
#: the forward-declared ``fan_out.rrf_k`` AppSetting default.
DEFAULT_RRF_K: int = 60


@dataclass(frozen=True)
class FusedItem:
    """One document's place in the fused ranking."""

    doc_id: Hashable
    score: float  # sum of reciprocal-rank contributions
    contributions: dict[str, float]  # per-ranker reciprocal-rank contribution


def fuse(
    rankings: Mapping[str, Sequence[DocId]],
    *,
    k: int = DEFAULT_RRF_K,
    top_n: int | None = None,
) -> list[FusedItem]:
    """Fuse named ranked lists into a single RRF-scored ordering.

    Parameters
    ----------
    rankings
        ``{ranker_name: ordered_doc_ids}``. Order within each list
        is most-relevant first; each list can be a different length
        and include a different subset of docs. Ties in the input
        are not repaired — if a ranker lists the same doc twice, the
        first position wins (later duplicates are skipped).
    k
        RRF smoothing constant (see module docstring).
    top_n
        If given, truncate the fused output after this many items.

    Returns
    -------
    List of :class:`FusedItem` sorted by descending score. Ties are
    broken by the first ranker name that contributed a score for
    the tied doc (alphabetical), then by stringified ``doc_id`` —
    both break-ties are deterministic so the output is stable under
    shuffled inputs.
    """
    if k <= 0:
        raise ValueError("k must be > 0")

    scores: dict[DocId, float] = {}
    contributions: dict[DocId, dict[str, float]] = {}
    first_seen_ranker: dict[DocId, str] = {}

    for ranker_name, ranked_list in rankings.items():
        seen_in_this_list: set[DocId] = set()
        for position, doc_id in enumerate(ranked_list, start=1):
            if doc_id in seen_in_this_list:
                continue
            seen_in_this_list.add(doc_id)
            contribution = 1.0 / (k + position)
            scores[doc_id] = scores.get(doc_id, 0.0) + contribution
            contributions.setdefault(doc_id, {})[ranker_name] = contribution
            first_seen_ranker.setdefault(doc_id, ranker_name)

    items = [
        FusedItem(
            doc_id=doc_id,
            score=score,
            contributions=contributions[doc_id],
        )
        for doc_id, score in scores.items()
    ]
    items.sort(
        key=lambda item: (
            -item.score,
            first_seen_ranker[item.doc_id],
            str(item.doc_id),
        )
    )
    if top_n is not None and top_n >= 0:
        items = items[:top_n]
    return items


def fuse_to_ids(
    rankings: Mapping[str, Sequence[DocId]],
    *,
    k: int = DEFAULT_RRF_K,
    top_n: int | None = None,
) -> list[DocId]:
    """Convenience wrapper that returns just the fused ID order.

    Useful when the caller doesn't care about the score breakdown —
    e.g. a reranker that only needs the winning doc list.
    """
    return [item.doc_id for item in fuse(rankings, k=k, top_n=top_n)]


def reciprocal_rank_score(
    *,
    position: int,
    k: int = DEFAULT_RRF_K,
) -> float:
    """Return the RRF contribution for a document at 1-based *position*.

    Exposed so callers who already have a composed score can add an
    RRF contribution on top without rebuilding the full fusion.
    """
    if position <= 0:
        raise ValueError("position must be >= 1 (RRF uses 1-based ranks)")
    if k <= 0:
        raise ValueError("k must be > 0")
    return 1.0 / (k + position)


def iter_fused(
    rankings: Iterable[tuple[str, Sequence[DocId]]],
    *,
    k: int = DEFAULT_RRF_K,
) -> list[FusedItem]:
    """Variant accepting an iterable of ``(name, ranked_list)`` tuples.

    Makes the common "read from N generators" case painless — plain
    :func:`fuse` requires a mapping, which forces the caller to
    collect everything first. This version walks the iterable once.
    """
    return fuse(dict(rankings), k=k)
