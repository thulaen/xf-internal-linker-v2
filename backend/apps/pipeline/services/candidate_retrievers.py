"""Stage-1 candidate retrieval as a list of pluggable retrievers.

Group C.1 refactors the original single-function ``_stage1_candidates``
into a ``CandidateRetriever`` protocol with concrete implementations.
The default registry has a single ``SemanticRetriever`` that does
exactly what the original code did (FAISS or NumPy cosine over BGE-M3
embeddings), so behaviour is unchanged at this commit.

Subsequent groups extend the registry without modifying the
machinery here:

- **Group C.2** adds ``LexicalRetriever`` (BM25 over destination titles
  + host content) and a Stage-1.5 fusion step using pick #31 RRF
  (Cormack et al. 2009).
- **Group C.3** adds ``QueryExpansionRetriever`` (pick #27) that runs
  over an expanded destination representation.

Why a list-of-retrievers + a unifier function rather than a deeper
inheritance hierarchy: each retriever is data-driven, has different
inputs (embeddings vs tokens vs expanded queries), and the unifier
is simple enough to keep as a free function. A class hierarchy
would force a common signature that doesn't fit BM25 (which doesn't
need embeddings).

Anti-Spaghetti Charter note: this module follows Pattern A (sidecar
contribution). Retrievers are constructed once per pipeline pass in
:mod:`apps.pipeline.services.pipeline` and passed through to
:func:`apps.pipeline.services.pipeline_stages._stage1_candidates`,
which delegates to :func:`run_retrievers` here. No new Django app,
no new C++ kernel, no parallel implementation of the FAISS path.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Iterable, Protocol

import numpy as np

from .ranker import ContentKey, ContentRecord

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class RetrievalContext:
    """Shared inputs every retriever may need.

    Bundled in a frozen dataclass so we can extend the surface area
    in Groups C.2/C.3 without changing the protocol signature.
    """

    destination_keys: tuple[ContentKey, ...]
    dest_embeddings: np.ndarray
    content_records: dict[ContentKey, ContentRecord]
    content_to_sentence_ids: dict[ContentKey, list[int]]
    top_k: int
    block_size: int


class CandidateRetriever(Protocol):
    """Returns ``dest_key → list[sentence_id]`` candidate-host mappings.

    Each retriever decides its own scoring backend (FAISS, BM25, …)
    but must return ordered lists of host sentence IDs per destination
    so the unifier can dedup-while-preserving-order.

    The ``name`` attribute identifies the retriever in logs +
    diagnostics + RRF fusion (Group C.2 reads it as a per-list label).
    """

    name: str

    def retrieve(
        self, context: RetrievalContext
    ) -> dict[ContentKey, list[int]]:
        ...


# ── Concrete: SemanticRetriever ──────────────────────────────────


class SemanticRetriever:
    """FAISS-or-NumPy cosine similarity over BGE-M3 embeddings.

    Wraps the original ``_stage1_candidates`` body so the refactor
    is byte-equivalent. Future C.2/C.3 retrievers don't touch this
    code path.
    """

    name: str = "semantic"

    def retrieve(
        self, context: RetrievalContext
    ) -> dict[ContentKey, list[int]]:
        # Inline import keeps the module load cheap when this
        # retriever isn't constructed (e.g. tests that stub the
        # registry).
        from .pipeline_stages import _stage1_semantic_candidates

        return _stage1_semantic_candidates(
            destination_keys=context.destination_keys,
            dest_embeddings=context.dest_embeddings,
            content_records=context.content_records,
            content_to_sentence_ids=context.content_to_sentence_ids,
            top_k=context.top_k,
            block_size=context.block_size,
        )


# ── Unifier ──────────────────────────────────────────────────────


def run_retrievers(
    retrievers: Iterable[CandidateRetriever],
    *,
    context: RetrievalContext,
) -> dict[ContentKey, list[int]]:
    """Run each retriever and union their candidate lists per destination.

    Group C.1 unification is the simplest possible: dedup while
    preserving each retriever's first-seen order, concatenated in
    retriever order. With a single ``SemanticRetriever`` this is
    identical to the legacy behaviour.

    Group C.2 will replace this with an RRF-weighted fusion step
    (pick #31). Until then, multi-retriever output is just the union
    — fine for callers that pass a single retriever, and a safe
    default when callers experiment with adding a second one before
    RRF lands.

    Diagnostics: each retriever's contribution count is logged at
    INFO so operators can see how the candidate pool was assembled.
    """
    retrievers_list = list(retrievers)
    if not retrievers_list:
        logger.warning("run_retrievers: empty retriever list — no candidates")
        return {}

    # Per-destination ordered list with dedup.
    out: dict[ContentKey, list[int]] = {}
    seen_per_dest: dict[ContentKey, set[int]] = {}

    for retriever in retrievers_list:
        try:
            partial = retriever.retrieve(context)
        except Exception:
            logger.exception(
                "run_retrievers: retriever %s raised — skipping its contribution",
                retriever.name,
            )
            continue
        contributed_total = 0
        for dest_key, sentence_ids in partial.items():
            if dest_key not in out:
                out[dest_key] = []
                seen_per_dest[dest_key] = set()
            seen = seen_per_dest[dest_key]
            for sid in sentence_ids:
                if sid in seen:
                    continue
                seen.add(sid)
                out[dest_key].append(sid)
                contributed_total += 1
        logger.info(
            "run_retrievers: %s contributed %d new candidates across %d destinations",
            retriever.name,
            contributed_total,
            len(partial),
        )
    return out


# ── Default registry ─────────────────────────────────────────────


def default_retrievers() -> list[CandidateRetriever]:
    """Return the production retriever list.

    Group C.1: a single :class:`SemanticRetriever`. Group C.2 will
    extend this to ``[SemanticRetriever(), LexicalRetriever()]`` plus
    an RRF fusion step. Keeping this construction in one function
    means callers don't need to know which retrievers are active —
    they just import and call.
    """
    return [SemanticRetriever()]
