"""Bag-of-words query expansion via pseudo-relevance feedback (Rocchio).

References
----------
- Rocchio, J. J. (1971). "Relevance feedback in information retrieval."
  *The SMART Retrieval System: Experiments in Automatic Document
  Processing*, pp. 313-323.
- Lavrenko, V. & Croft, W. B. (2001). "Relevance-based language models."
  *Proceedings of the 24th ACM SIGIR Conference*, pp. 120-127.

Goal
----
After a first retrieval pass ranks a handful of documents for the user's
query, use those top-N results as *pseudo-relevant* evidence to discover
extra terms that co-occur with the query topic. Feed that expanded bag
back into the retriever to catch documents that use synonyms or
related vocabulary (the classic "vocabulary mismatch" problem).

This module does **only** the math — it doesn't run the retriever, it
doesn't touch the DB. Callers hand in term-frequency vectors for the
top-N pseudo-relevant docs, and get back a ranked list of expansion
terms plus a recommended new query weighting. The ranker can then re-run
its existing BM25 / cosine pass with the expanded query.

Why not scikit-learn's ``TfidfVectorizer``?
  We already have BM25 / field-aware scoring elsewhere; this helper
  stays tiny and vocabulary-agnostic so callers control tokenisation.

The module is pure Python + the stdlib. No numpy requirement — PRF is
over small document sets (N = 10-30), so a dict/Counter is plenty
fast and keeps the helper trivially testable.
"""

from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping


#: Number of pseudo-relevant docs to inspect. Rocchio's original paper
#: and most modern TREC work settle around 10; values above ~30 mostly
#: add noise because the later docs tend to be off-topic.
DEFAULT_TOP_N: int = 10

#: Number of expansion terms to keep after scoring. Lavrenko-Croft RM1
#: found that more than 20 expansion terms rarely helps — the ranker
#: starts drifting toward the documents instead of the query.
DEFAULT_EXPANSION_TERMS: int = 10

#: Rocchio's α (original-query weight). Values in [0.6, 1.2] are
#: common — 1.0 means "trust the user's query as much as the
#: pseudo-relevant evidence."
DEFAULT_ALPHA: float = 1.0

#: Rocchio's β (relevant-centroid weight). 0.5-0.8 is the canonical
#: range; above 1.0 the expanded query loses touch with the user's
#: original intent.
DEFAULT_BETA: float = 0.75


@dataclass(frozen=True)
class ExpansionTerm:
    """One candidate expansion term with its Rocchio score."""

    term: str
    score: float
    document_frequency: int  # how many of the pseudo-relevant docs contained it


@dataclass(frozen=True)
class ExpandedQuery:
    """Final Rocchio-weighted query vector.

    Maps term → weight. Original-query terms appear with weight roughly
    ``alpha``; expansion terms appear with weight proportional to
    ``beta * pseudo-relevant frequency``.
    """

    weights: dict[str, float] = field(default_factory=dict)
    expansion_terms: list[ExpansionTerm] = field(default_factory=list)


def rank_expansion_terms(
    pseudo_relevant_docs: Iterable[Mapping[str, int]],
    *,
    query_terms: set[str],
    top_terms: int = DEFAULT_EXPANSION_TERMS,
    stopwords: frozenset[str] = frozenset(),
    min_document_frequency: int = 2,
) -> list[ExpansionTerm]:
    """Return the *top_terms* expansion candidates ranked by Rocchio score.

    Parameters
    ----------
    pseudo_relevant_docs
        Iterable of term-frequency mappings, one per top-N retrieved
        doc. Keys are already-tokenised terms (the caller picks the
        tokeniser); values are raw counts.
    query_terms
        The original query's terms, used to exclude them from the
        expansion set so they don't get double-counted.
    top_terms
        Maximum number of expansion candidates to return.
    stopwords
        Terms to skip outright. Pass the same stopword list the retriever
        uses so the expanded query stays consistent.
    min_document_frequency
        A candidate must appear in at least this many pseudo-relevant
        docs — solo-doc terms are noise. Rocchio's paper used 2.
    """
    docs = list(pseudo_relevant_docs)
    if not docs:
        return []

    term_doc_freq: Counter[str] = Counter()
    term_total_count: Counter[str] = Counter()
    for doc in docs:
        for term, count in doc.items():
            if count <= 0 or term in query_terms or term in stopwords:
                continue
            term_doc_freq[term] += 1
            term_total_count[term] += count

    candidates: list[ExpansionTerm] = []
    total_docs = len(docs)
    for term, df in term_doc_freq.items():
        if df < min_document_frequency:
            continue
        # Rocchio's centroid component: avg tf across relevant docs.
        avg_tf = term_total_count[term] / total_docs
        # Boost terms that appeared in more docs — broadly-used in the
        # relevant set, more likely on-topic.
        breadth = math.log1p(df)
        score = avg_tf * breadth
        candidates.append(
            ExpansionTerm(
                term=term,
                score=score,
                document_frequency=df,
            )
        )

    candidates.sort(key=lambda c: (-c.score, c.term))
    return candidates[:top_terms]


def build_expanded_query(
    original_query_weights: Mapping[str, float],
    expansion_terms: Iterable[ExpansionTerm],
    *,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
) -> ExpandedQuery:
    """Merge the user's query with the expansion terms via Rocchio weights.

    Output weights::

        W(t) = alpha * original_weight(t) + beta * expansion_score(t)

    Terms only in the original query keep ``alpha * w``; terms only in
    the expansion list get ``beta * s``; terms in both get the sum.

    Non-negative inputs produce non-negative outputs (negative weights
    aren't meaningful for BoW retrieval — Rocchio's original paper's
    γ-weighted *non-relevant* term is excluded on purpose).
    """
    if alpha < 0 or beta < 0:
        raise ValueError("alpha and beta must be non-negative")

    weights: dict[str, float] = {}
    for term, w in original_query_weights.items():
        if w <= 0:
            continue
        weights[term] = alpha * w

    expansion_list = list(expansion_terms)
    for exp in expansion_list:
        if exp.score <= 0:
            continue
        weights[exp.term] = weights.get(exp.term, 0.0) + beta * exp.score

    return ExpandedQuery(
        weights=weights,
        expansion_terms=expansion_list,
    )


def expand(
    *,
    original_query_weights: Mapping[str, float],
    pseudo_relevant_docs: Iterable[Mapping[str, int]],
    top_terms: int = DEFAULT_EXPANSION_TERMS,
    alpha: float = DEFAULT_ALPHA,
    beta: float = DEFAULT_BETA,
    stopwords: frozenset[str] = frozenset(),
    min_document_frequency: int = 2,
) -> ExpandedQuery:
    """Convenience wrapper: rank expansion terms and merge in one call.

    This is the common entrypoint — :func:`rank_expansion_terms` and
    :func:`build_expanded_query` are exposed for callers who want to
    inspect or filter the expansion set between the two steps.
    """
    query_terms = {t for t, w in original_query_weights.items() if w > 0}
    terms = rank_expansion_terms(
        pseudo_relevant_docs,
        query_terms=query_terms,
        top_terms=top_terms,
        stopwords=stopwords,
        min_document_frequency=min_document_frequency,
    )
    return build_expanded_query(
        original_query_weights,
        terms,
        alpha=alpha,
        beta=beta,
    )
