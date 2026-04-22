"""Query-likelihood retrieval with Dirichlet smoothing (Zhai-Lafferty 2001).

Reference
---------
Zhai, C. & Lafferty, J. (2001). "A study of smoothing methods for
language models applied to ad hoc information retrieval."
*Proceedings of the 24th ACM SIGIR Conference*, pp. 334-342.

Goal
----
Score a document against a query as the log-probability the document's
language model (LM) would have generated the query::

    score(Q, D) = Σ_t_in_Q  count(t, Q) * log P(t | θ_D)

where ``θ_D`` is the Dirichlet-smoothed LM::

    P(t | θ_D) = ( count(t, D) + μ * P(t | C) ) / ( |D| + μ )

``P(t | C)`` is the collection-wide (background) probability of term
``t``. ``μ`` is the smoothing mass — higher ``μ`` pulls the doc LM
toward the corpus average, which matters for short docs (a single
irrelevant term can dominate an un-smoothed LM).

Zhai-Lafferty's empirical result: Dirichlet smoothing with μ ≈ 2000
works well across TREC benchmarks and pairs well with BM25 via
ranked-list fusion (see :mod:`apps.pipeline.services.query_expansion_bow`
and the plan's pick #31 — Reciprocal Rank Fusion).

Why not reuse :mod:`apps.pipeline.services.keyword_stuffing`?
  That module *also* uses a Dirichlet-smoothed LM, but for a totally
  different purpose: it computes KL divergence between a doc's LM and
  the corpus baseline to flag keyword-stuffed content. The math shape
  is similar, the intent is opposite. Sharing code would tangle a
  spam-detector with a relevance scorer — two separate modules keeps
  the contracts clean.

Pure Python + ``math`` only — no numpy. The inner loop iterates over
query terms, not collection terms, so a dict is plenty fast. All
operations are deterministic for the same inputs.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass
from typing import Mapping


#: Default Dirichlet smoothing mass (Zhai-Lafferty 2001 §5.2). Values
#: in [500, 3000] are all reasonable; 2000 is the commonly-cited
#: sweet spot for mixed-length TREC-style documents.
DEFAULT_DIRICHLET_MU: float = 2000.0

#: Floor on collection probability to prevent ``log(0)`` when a query
#: term doesn't appear in the corpus at all. Using an ε of 1e-10 means
#: an unseen term contributes ~-23 to the log-score, which is
#: enough to rank docs that do contain the term clearly higher.
_MIN_COLLECTION_PROBABILITY: float = 1e-10


@dataclass(frozen=True)
class CollectionStatistics:
    """Corpus-level frequency statistics used for smoothing.

    ``collection_term_counts`` is the total occurrence count for each
    term across the entire corpus; ``collection_length`` is the sum of
    those counts (equivalently, the total number of term occurrences).
    These are typically precomputed once and reused across queries.
    """

    collection_term_counts: Mapping[str, int]
    collection_length: int

    def __post_init__(self) -> None:
        if self.collection_length <= 0:
            raise ValueError("collection_length must be > 0")


@dataclass(frozen=True)
class QueryLikelihoodScore:
    """Result of :func:`score_document`.

    ``log_score`` is always ≤ 0 (it's a sum of log-probabilities).
    ``per_term`` lets callers audit which query terms contributed
    most to the score — handy for debugging/explainability.
    """

    log_score: float
    per_term: dict[str, float]


def collection_probability(
    term: str,
    statistics: CollectionStatistics,
) -> float:
    """Return ``P(t | C)``, floored at ``_MIN_COLLECTION_PROBABILITY``."""
    count = statistics.collection_term_counts.get(term, 0)
    if count <= 0:
        return _MIN_COLLECTION_PROBABILITY
    return max(count / statistics.collection_length, _MIN_COLLECTION_PROBABILITY)


def dirichlet_smoothed_probability(
    *,
    term: str,
    document_term_counts: Mapping[str, int],
    document_length: int,
    statistics: CollectionStatistics,
    mu: float = DEFAULT_DIRICHLET_MU,
) -> float:
    """Return ``P(t | θ_D)`` under Dirichlet smoothing.

    Works for terms that don't appear in the document (count = 0) —
    the smoothing term carries the collection probability through.
    """
    if mu < 0:
        raise ValueError("mu must be >= 0")
    doc_count = document_term_counts.get(term, 0)
    collection_prob = collection_probability(term, statistics)
    numerator = doc_count + mu * collection_prob
    denominator = document_length + mu
    if denominator <= 0:
        return collection_prob
    return numerator / denominator


def score_document(
    *,
    query_term_counts: Mapping[str, int],
    document_term_counts: Mapping[str, int],
    document_length: int,
    statistics: CollectionStatistics,
    mu: float = DEFAULT_DIRICHLET_MU,
) -> QueryLikelihoodScore:
    """Score a document against a query under Dirichlet-smoothed QL.

    The score is a sum of log-probabilities; comparing two docs'
    scores for the same query tells you which one the LM prefers.
    Scores from different queries are **not** comparable on an
    absolute scale — they depend on the query's term counts.

    Empty query → score of 0.0 (degenerate but well-defined).
    """
    log_score = 0.0
    per_term: dict[str, float] = {}
    for term, q_count in query_term_counts.items():
        if q_count <= 0:
            continue
        p = dirichlet_smoothed_probability(
            term=term,
            document_term_counts=document_term_counts,
            document_length=document_length,
            statistics=statistics,
            mu=mu,
        )
        contribution = q_count * math.log(p)
        per_term[term] = contribution
        log_score += contribution
    return QueryLikelihoodScore(log_score=log_score, per_term=per_term)


def tokenised_to_counter(tokens) -> Counter[str]:
    """Convenience: turn a token iterable into a :class:`Counter`.

    Provided so callers don't have to import :mod:`collections` just
    to prepare inputs for :func:`score_document`.
    """
    return Counter(tokens)
