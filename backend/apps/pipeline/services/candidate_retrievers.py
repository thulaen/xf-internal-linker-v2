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


# ── Lexical/QueryExpansion shared token-bag helpers (C.2 + C.3) ─


def _build_token_set(text: str, *, min_length: int) -> set[str]:
    """Tokenise *text*; drop short tokens + standard English stopwords.

    Shared between :class:`LexicalRetriever` and
    :class:`QueryExpansionRetriever` so they stay vocabulary-aligned.
    """
    if not text:
        return set()
    from .text_tokens import STANDARD_ENGLISH_STOPWORDS, TOKEN_RE

    out: set[str] = set()
    for raw in TOKEN_RE.findall(text.lower()):
        if len(raw) < min_length:
            continue
        if raw in STANDARD_ENGLISH_STOPWORDS:
            continue
        out.add(raw)
    return out


def _build_host_token_bags(
    context: RetrievalContext, *, min_length: int
) -> dict[ContentKey, set[str]]:
    """Build ``{host_key: token_set}`` from titles + scope titles.

    Only emits hosts that have at least one usable token *and* a
    non-empty sentence-ID list — sources that can't contribute
    candidates are filtered out at the bag-build stage.
    """
    host_tokens: dict[ContentKey, set[str]] = {}
    for key, record in context.content_records.items():
        if key not in context.content_to_sentence_ids:
            continue
        if not context.content_to_sentence_ids[key]:
            continue
        title = getattr(record, "title", "") or ""
        scope = getattr(record, "scope_title", "") or ""
        tokens = _build_token_set(title, min_length=min_length) | _build_token_set(
            scope, min_length=min_length
        )
        if tokens:
            host_tokens[key] = tokens
    return host_tokens


def _rank_hosts_by_overlap(
    *,
    query_tokens: set[str],
    host_tokens: dict[ContentKey, set[str]],
    skip_key: ContentKey,
    host_keys_ordered: list[ContentKey],
    top_k: int,
) -> list[ContentKey]:
    """Return the top-K hosts ranked by token-overlap with *query_tokens*.

    Ties broken on the host's index in ``host_keys_ordered`` for
    determinism. ``skip_key`` is excluded (typically the destination
    itself, so the retriever doesn't return a self-link).
    """
    scored: list[tuple[int, int, ContentKey]] = []
    for idx, host_key in enumerate(host_keys_ordered):
        if host_key == skip_key:
            continue
        overlap = len(query_tokens & host_tokens[host_key])
        if overlap == 0:
            continue
        scored.append((-overlap, idx, host_key))
    if not scored:
        return []
    scored.sort()
    return [hk for _, _, hk in scored[:top_k]]


# ── Concrete: LexicalRetriever (Group C.2) ───────────────────────


class LexicalRetriever:
    """Token-overlap lexical retriever over destination & content titles.

    Complements :class:`SemanticRetriever` by surfacing host content
    that shares **lexical** signal with the destination title — the
    classic "synonym vs spelling-out" gap that dense embeddings can
    miss when the user's query exactly matches a known phrase.

    Algorithm
    ---------
    1. Tokenise each destination title via :mod:`text_tokens` and
       drop standard stopwords + tokens shorter than ``min_token_length``.
    2. For each destination, score every host content record by the
       size of the title-token intersection (Jaccard-without-the-divide
       — pure intersection size, since RRF only uses ranks). Tie-break
       on host record index for determinism.
    3. Take the top-K hosts and emit their full sentence-ID lists,
       mirroring the semantic path's contract.

    Feature-flagged off by default; enable via the AppSetting
    ``stage1.lexical_retriever_enabled``. Cold-start safe.
    """

    name: str = "lexical"

    def __init__(self, *, enabled: bool = False, min_token_length: int = 3):
        self.enabled = enabled
        self.min_token_length = min_token_length

    def retrieve(
        self, context: RetrievalContext
    ) -> dict[ContentKey, list[int]]:
        if not self.enabled:
            return {}

        host_tokens = _build_host_token_bags(
            context, min_length=self.min_token_length
        )
        if not host_tokens:
            return {}
        host_keys_ordered = list(host_tokens.keys())

        result: dict[ContentKey, list[int]] = {}
        for dest_key in context.destination_keys:
            dest_record = context.content_records.get(dest_key)
            if dest_record is None:
                continue
            dest_title = getattr(dest_record, "title", "") or ""
            dest_scope = getattr(dest_record, "scope_title", "") or ""
            dest_token_set = _build_token_set(
                dest_title, min_length=self.min_token_length
            ) | _build_token_set(dest_scope, min_length=self.min_token_length)
            if not dest_token_set:
                continue

            top_hosts = _rank_hosts_by_overlap(
                query_tokens=dest_token_set,
                host_tokens=host_tokens,
                skip_key=dest_key,
                host_keys_ordered=host_keys_ordered,
                top_k=context.top_k,
            )
            sentence_ids: list[int] = []
            for host_key in top_hosts:
                sentence_ids.extend(
                    context.content_to_sentence_ids.get(host_key, [])
                )
            if sentence_ids:
                result[dest_key] = sentence_ids
        return result


# ── Concrete: QueryExpansionRetriever (Group C.3) ─────────────────


class QueryExpansionRetriever:
    """Pseudo-relevance-feedback lexical retriever (pick #27).

    The classic Rocchio (1971) / Lavrenko-Croft (2001) PRF cycle:

    1. Use the destination title tokens as the *original query*.
    2. Run a first lexical pass — find the top-N pseudo-relevant
       hosts by plain token-overlap (same algorithm as
       :class:`LexicalRetriever`).
    3. Treat those N hosts as evidence; rank co-occurring tokens by
       :func:`query_expansion_bow.rank_expansion_terms` (Rocchio
       weighting) to discover synonyms / related-vocabulary terms.
    4. Re-run the lexical pass with the *expanded* query
       (original + top-K expansion terms) to surface hosts that
       didn't share the literal title tokens.

    Why this complements semantic + plain-lexical:
    - SemanticRetriever already handles synonyms via dense
      embeddings. PRF gives a second, **interpretable** path —
      the operator can see exactly which expansion terms pulled
      a host into the candidate pool (Group C.3 diagnostics in a
      future commit will surface them).
    - Different rank order ⇒ adds value to RRF fusion.
    - Pure Python + the existing helpers; no new pip dep.

    Feature-flagged off by default via the AppSetting
    ``stage1.query_expansion_retriever_enabled``. Cold-start safe at
    every layer: no destinations / no host tokens / too few
    pseudo-relevant docs → returns ``{}`` for that destination.
    """

    name: str = "query_expansion"

    def __init__(
        self,
        *,
        enabled: bool = False,
        min_token_length: int = 3,
        prf_top_n: int = 10,
        expansion_terms: int = 10,
        min_document_frequency: int = 2,
    ):
        self.enabled = enabled
        self.min_token_length = min_token_length
        self.prf_top_n = prf_top_n
        self.expansion_terms = expansion_terms
        self.min_document_frequency = min_document_frequency

    def retrieve(
        self, context: RetrievalContext
    ) -> dict[ContentKey, list[int]]:
        if not self.enabled:
            return {}

        from collections import Counter

        from .query_expansion_bow import rank_expansion_terms
        from .text_tokens import STANDARD_ENGLISH_STOPWORDS

        host_tokens = _build_host_token_bags(
            context, min_length=self.min_token_length
        )
        if not host_tokens:
            return {}
        host_keys_ordered = list(host_tokens.keys())
        stopwords_frozen = frozenset(STANDARD_ENGLISH_STOPWORDS)

        result: dict[ContentKey, list[int]] = {}
        for dest_key in context.destination_keys:
            dest_record = context.content_records.get(dest_key)
            if dest_record is None:
                continue
            dest_title = getattr(dest_record, "title", "") or ""
            dest_scope = getattr(dest_record, "scope_title", "") or ""
            dest_token_set = _build_token_set(
                dest_title, min_length=self.min_token_length
            ) | _build_token_set(dest_scope, min_length=self.min_token_length)
            if not dest_token_set:
                continue

            # Step 1 — first lexical pass to find pseudo-relevant docs.
            prf_hosts = _rank_hosts_by_overlap(
                query_tokens=dest_token_set,
                host_tokens=host_tokens,
                skip_key=dest_key,
                host_keys_ordered=host_keys_ordered,
                top_k=self.prf_top_n,
            )

            # Step 2 — derive expansion terms from those docs (when
            # we have enough). With < 2 PRF docs Rocchio collapses
            # toward noise; fall back to the plain lexical query.
            expanded_tokens = set(dest_token_set)
            if len(prf_hosts) >= 2:
                prf_term_counts: list[Counter] = [
                    Counter({tok: 1 for tok in host_tokens[host_key]})
                    for host_key in prf_hosts
                ]
                expansion_records = rank_expansion_terms(
                    prf_term_counts,
                    query_terms=dest_token_set,
                    top_terms=self.expansion_terms,
                    stopwords=stopwords_frozen,
                    min_document_frequency=self.min_document_frequency,
                )
                for record in expansion_records:
                    if (
                        record.term not in dest_token_set
                        and len(record.term) >= self.min_token_length
                    ):
                        expanded_tokens.add(record.term)

            # Step 3 — rank hosts using the expanded query.
            top_hosts = _rank_hosts_by_overlap(
                query_tokens=expanded_tokens,
                host_tokens=host_tokens,
                skip_key=dest_key,
                host_keys_ordered=host_keys_ordered,
                top_k=context.top_k,
            )

            sentence_ids: list[int] = []
            for host_key in top_hosts:
                sentence_ids.extend(
                    context.content_to_sentence_ids.get(host_key, [])
                )
            if sentence_ids:
                result[dest_key] = sentence_ids
        return result


# ── Unifier ──────────────────────────────────────────────────────


def run_retrievers(
    retrievers: Iterable[CandidateRetriever],
    *,
    context: RetrievalContext,
    fuse_with_rrf: bool = True,
    rrf_k: int | None = None,
) -> dict[ContentKey, list[int]]:
    """Run each retriever and unify their candidate lists per destination.

    Two unification modes:

    1. **Single retriever** — pass-through. The retriever's per-dest
       output is returned verbatim.
    2. **Multiple retrievers + ``fuse_with_rrf=True`` (default)** —
       Group C.2 fuses each per-dest list via Reciprocal Rank Fusion
       (Cormack et al. 2009, pick #31). Each retriever's list is
       treated as a separate ranking; per-dest, the unified order is
       the RRF-fused permutation of every contributed sentence ID.
       This is parameter-free (save ``k=60``) and lets the lexical
       retriever's strong matches surface even when the semantic
       retriever's cosine ranks them lower (and vice-versa).
    3. **Multiple retrievers + ``fuse_with_rrf=False``** — fallback
       to the simpler dedup-while-preserving-order union from C.1.
       Tests use this to assert the abstraction works without
       depending on the RRF helper.

    ``rrf_k`` overrides the smoothing constant; defaults to the
    helper's pick-31 default of 60. A failing retriever is logged
    and skipped without poisoning the others.
    """
    retrievers_list = list(retrievers)
    if not retrievers_list:
        logger.warning("run_retrievers: empty retriever list — no candidates")
        return {}

    # Collect each retriever's per-dest output. Skip exceptions.
    contributions: list[tuple[str, dict[ContentKey, list[int]]]] = []
    for retriever in retrievers_list:
        try:
            partial = retriever.retrieve(context)
        except Exception:
            logger.exception(
                "run_retrievers: retriever %s raised — skipping its contribution",
                retriever.name,
            )
            continue
        contributions.append((retriever.name, partial))
        logger.info(
            "run_retrievers: %s returned %d destinations with candidates",
            retriever.name,
            len(partial),
        )

    if not contributions:
        return {}
    if len(contributions) == 1:
        # Single retriever — short-circuit, behaviour-equivalent to
        # the legacy single-source path.
        return contributions[0][1]

    if fuse_with_rrf:
        return _fuse_via_rrf(contributions, k=rrf_k)
    return _union_dedup_preserving_order(contributions)


def _union_dedup_preserving_order(
    contributions: list[tuple[str, dict[ContentKey, list[int]]]],
) -> dict[ContentKey, list[int]]:
    """Group C.1 dedup-preserving-order union (kept for tests and fallback)."""
    out: dict[ContentKey, list[int]] = {}
    seen_per_dest: dict[ContentKey, set[int]] = {}
    for _, partial in contributions:
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
    return out


def _fuse_via_rrf(
    contributions: list[tuple[str, dict[ContentKey, list[int]]]],
    *,
    k: int | None,
) -> dict[ContentKey, list[int]]:
    """RRF-fuse per-destination rankings via :mod:`reciprocal_rank_fusion`."""
    from .reciprocal_rank_fusion import DEFAULT_RRF_K, fuse

    rrf_k = k if k is not None else DEFAULT_RRF_K

    # Index destinations that any retriever produced for.
    all_dest_keys: set[ContentKey] = set()
    for _, partial in contributions:
        all_dest_keys.update(partial.keys())

    out: dict[ContentKey, list[int]] = {}
    for dest_key in all_dest_keys:
        rankings: dict[str, list[int]] = {}
        for retriever_name, partial in contributions:
            sentence_ids = partial.get(dest_key)
            if sentence_ids:
                rankings[retriever_name] = list(sentence_ids)
        if not rankings:
            continue
        # Single-source per dest → preserve the source's order
        # exactly. ``fuse`` would still produce that order, but the
        # short-circuit avoids the per-call dict-construction cost.
        if len(rankings) == 1:
            only_name = next(iter(rankings))
            out[dest_key] = list(rankings[only_name])
            continue
        fused = fuse(rankings, k=rrf_k)
        out[dest_key] = [item.doc_id for item in fused]
    return out


# ── Default registry ─────────────────────────────────────────────


def default_retrievers() -> list[CandidateRetriever]:
    """Return the production retriever list.

    Always-on:
    - :class:`SemanticRetriever` (the legacy default).

    Opt-in via AppSetting:
    - :class:`LexicalRetriever` — flipped on by
      ``stage1.lexical_retriever_enabled``.
    - :class:`QueryExpansionRetriever` — flipped on by
      ``stage1.query_expansion_retriever_enabled``.

    When more than one retriever is active, :func:`run_retrievers`
    automatically uses RRF (#31) to fuse the per-dest ranked lists.
    Both opt-ins are independent — operators can enable any subset.
    """
    retrievers: list[CandidateRetriever] = [SemanticRetriever()]
    if _setting_enabled("stage1.lexical_retriever_enabled"):
        retrievers.append(LexicalRetriever(enabled=True))
    if _setting_enabled("stage1.query_expansion_retriever_enabled"):
        retrievers.append(QueryExpansionRetriever(enabled=True))
    return retrievers


def _setting_enabled(key: str) -> bool:
    """Read a boolean AppSetting flag with cold-start fallback to False.

    Catches every conceivable failure mode (Django not initialised,
    AppSetting model missing, DB unreachable, migration not applied,
    ``SimpleTestCase`` DatabaseOperationForbidden guard) and returns
    False. Opt-in retrievers stay off until the operator deliberately
    flips them on.
    """
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
    except Exception:
        return False
    if row is None or not row.value:
        return False
    return str(row.value).strip().lower() in {"1", "true", "yes", "on"}
