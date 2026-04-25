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


# ── Concrete: LexicalRetriever (Group C.2) ───────────────────────


class LexicalRetriever:
    """Token-overlap lexical retriever over destination & content titles.

    Complements :class:`SemanticRetriever` by surfacing host content
    that shares **lexical** signal with the destination title — the
    classic "synonym vs spelling-out" gap that dense embeddings can
    miss when the user's query exactly matches a known phrase.

    Algorithm
    ---------
    1. Tokenise each destination title via :func:`text_tokens.tokenize`
       and drop standard stopwords + tokens shorter than 3 chars.
    2. For each destination, score every host content record by the
       size of the title-token intersection (Jaccard-without-the-divide
       — pure intersection size, since RRF only uses ranks). Tie-break
       on host record index for determinism.
    3. Take the top-K hosts and emit their full sentence-ID lists,
       mirroring the semantic path's contract.

    This is intentionally simple: no DB query, no new dependency.
    Token overlap is a weak BM25 substitute but a real **second
    rank order**, which is exactly what RRF (#31) needs in order to
    add value over a single source. When the
    ``stage1.lexical_retriever_enabled`` setting is False the
    retriever returns ``{}`` and contributes nothing — making C.2
    feature-flagged off by default until operators enable it.

    Cold-start safe: empty content_records → empty output; no
    destinations have titles → empty output; lexicalised titles
    overlap zero hosts → no candidates for that destination.
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

        from .text_tokens import STANDARD_ENGLISH_STOPWORDS, TOKEN_RE

        def _tokens(text: str) -> set[str]:
            if not text:
                return set()
            out: set[str] = set()
            for raw in TOKEN_RE.findall(text.lower()):
                if len(raw) < self.min_token_length:
                    continue
                if raw in STANDARD_ENGLISH_STOPWORDS:
                    continue
                out.add(raw)
            return out

        # Build host token bags, indexed by content key.
        host_tokens: dict[ContentKey, set[str]] = {}
        for key, record in context.content_records.items():
            if key not in context.content_to_sentence_ids:
                continue
            if not context.content_to_sentence_ids[key]:
                continue
            title = getattr(record, "title", "") or ""
            scope = getattr(record, "scope_title", "") or ""
            tokens = _tokens(title) | _tokens(scope)
            if tokens:
                host_tokens[key] = tokens

        if not host_tokens:
            return {}

        result: dict[ContentKey, list[int]] = {}
        # Stable host iteration order so ties break deterministically.
        host_keys_ordered = list(host_tokens.keys())

        for dest_key in context.destination_keys:
            dest_record = context.content_records.get(dest_key)
            if dest_record is None:
                continue
            dest_title = getattr(dest_record, "title", "") or ""
            dest_scope = getattr(dest_record, "scope_title", "") or ""
            dest_token_set = _tokens(dest_title) | _tokens(dest_scope)
            if not dest_token_set:
                continue

            # Score every host by intersection size; skip self.
            scored: list[tuple[int, int, ContentKey]] = []
            for idx, host_key in enumerate(host_keys_ordered):
                if host_key == dest_key:
                    continue
                overlap = len(dest_token_set & host_tokens[host_key])
                if overlap == 0:
                    continue
                # Sort key: -overlap (higher first), then idx (stable).
                scored.append((-overlap, idx, host_key))

            if not scored:
                continue
            scored.sort()
            top_hosts = [hk for _, _, hk in scored[: context.top_k]]
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

    Group C.2: ``[SemanticRetriever(), LexicalRetriever(...)]`` when
    the AppSetting ``stage1.lexical_retriever_enabled`` is True,
    otherwise just ``[SemanticRetriever()]``. The lexical retriever
    is feature-flagged off by default — operators flip it on once
    they're comfortable with the RRF fusion path. When flipped on,
    :func:`run_retrievers` automatically uses RRF (#31) to fuse the
    two ranked lists per destination.
    """
    retrievers: list[CandidateRetriever] = [SemanticRetriever()]
    if _lexical_enabled():
        retrievers.append(LexicalRetriever(enabled=True))
    return retrievers


def _lexical_enabled() -> bool:
    """Read the on/off switch for the lexical retriever from AppSetting.

    Cold-start safe at every layer: any exception during the lookup
    (Django not initialised, AppSetting model missing, DB
    unreachable, migration not applied, ``SimpleTestCase``'s
    DatabaseOperationForbidden guard) returns False. The retriever
    stays opt-in; failures only ever bias toward "disabled".
    """
    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(
            key="stage1.lexical_retriever_enabled"
        ).first()
    except Exception:
        return False
    if row is None or not row.value:
        return False
    return str(row.value).strip().lower() in {"1", "true", "yes", "on"}
