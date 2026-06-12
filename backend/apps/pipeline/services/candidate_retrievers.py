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

_DEFAULT_ON_SETTING_KEYS = frozenset(
    (
        "stage1.lexical_retriever_enabled",
        "stage1.xenforo_bm25_retriever_enabled",
        "stage1.tantivy_bm25_retriever_enabled",
    )
)


@dataclass
class RetrievalContext:
    """Shared inputs every retriever may need.

    Bundled in a dataclass so we can extend the surface area in
    Groups C.2/C.3 without changing the protocol signature.

    *Mutable on purpose:* the per-pass token-bag cache
    (``_host_token_bags_cache``) lives on the context so two
    retrievers in the same run share the cost of tokenising every
    host's title + scope. See A.1 in the compute-waste plan.
    """

    destination_keys: tuple[ContentKey, ...]
    dest_embeddings: np.ndarray
    content_records: dict[ContentKey, ContentRecord]
    content_to_sentence_ids: dict[ContentKey, list[int]]
    top_k: int
    block_size: int
    #: Lazily-filled cache of host-key → token bag, keyed by the
    #: ``min_length`` parameter so multiple retrievers using
    #: different token-length floors don't collide. Filled by
    #: :func:`_build_host_token_bags` on first call. ``None`` until
    #: any retriever asks for tokens.
    _host_token_bags_cache: dict[int, dict[ContentKey, set[str]]] | None = None


class CandidateRetriever(Protocol):
    """Returns ``dest_key → list[sentence_id]`` candidate-host mappings.

    Each retriever decides its own scoring backend (FAISS, BM25, …)
    but must return ordered lists of host sentence IDs per destination
    so the unifier can dedup-while-preserving-order.

    The ``name`` attribute identifies the retriever in logs +
    diagnostics + RRF fusion (Group C.2 reads it as a per-list label).
    """

    name: str

    def retrieve(self, context: RetrievalContext) -> dict[ContentKey, list[int]]: ...


# ── Concrete: SemanticRetriever ──────────────────────────────────


class SemanticRetriever:
    """FAISS-or-NumPy cosine similarity over BGE-M3 embeddings.

    Wraps the original ``_stage1_candidates`` body so the refactor
    is byte-equivalent. Future C.2/C.3 retrievers don't touch this
    code path.
    """

    name: str = "semantic"

    def retrieve(self, context: RetrievalContext) -> dict[ContentKey, list[int]]:
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

    A.1: the result is cached on ``context._host_token_bags_cache``
    keyed by ``min_length``. When LexicalRetriever and
    QueryExpansionRetriever both run, the second call short-circuits
    to the cached dict instead of re-tokenising every host.
    """
    if context._host_token_bags_cache is None:
        context._host_token_bags_cache = {}
    cached = context._host_token_bags_cache.get(min_length)
    if cached is not None:
        return cached
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
    context._host_token_bags_cache[min_length] = host_tokens
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

    A.2: top-K selection uses ``heapq.nsmallest`` so the cost is
    O(H · log K) instead of the O(H · log H) we'd pay if we sorted
    the full scored list. At H = 50k hosts and K = 10, that's a ~4×
    speed-up per destination per retriever. The output ordering is
    identical to the prior full-sort path because we sort the K
    survivors at the end (heapq doesn't guarantee ordering of its
    output beyond "smallest first").
    """
    import heapq

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
    if len(scored) <= top_k:
        # Cheaper to sort directly than build a heap when we'll
        # return everything anyway.
        scored.sort()
        return [hk for _, _, hk in scored]
    # heapq.nsmallest internally builds a heap of size K and sorts
    # the survivors before returning, so the resulting order is
    # byte-identical to scored.sort()[:top_k] above.
    top = heapq.nsmallest(top_k, scored)
    return [hk for _, _, hk in top]


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

    def retrieve(self, context: RetrievalContext) -> dict[ContentKey, list[int]]:
        if not self.enabled:
            return {}

        host_tokens = _build_host_token_bags(context, min_length=self.min_token_length)
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
                sentence_ids.extend(context.content_to_sentence_ids.get(host_key, []))
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

    def retrieve(self, context: RetrievalContext) -> dict[ContentKey, list[int]]:
        if not self.enabled:
            return {}

        from collections import Counter

        from .query_expansion_bow import rank_expansion_terms
        from .text_tokens import STANDARD_ENGLISH_STOPWORDS

        host_tokens = _build_host_token_bags(context, min_length=self.min_token_length)
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
                sentence_ids.extend(context.content_to_sentence_ids.get(host_key, []))
            if sentence_ids:
                result[dest_key] = sentence_ids
        return result


# ── Concrete: XenForoBM25Retriever (XF Enhanced Search) ──────────


class XenForoBM25Retriever:
    """Hybrid-retrieval keyword companion backed by XenForo Elasticsearch.

    The XenForo forum we already import from runs Elasticsearch via the
    Enhanced Search add-on. This retriever queries it through the same
    REST API key the importer uses (no new server, no new auth, no new
    firewall hole) and returns BM25-ranked candidate hosts that the
    semantic retriever might miss — typically exact-keyword matches:
    product names, version strings, jargon, acronyms.

    Algorithm
    ---------
    1. For each destination, build a query string from
       ``ContentRecord.title`` (plus ``scope_title`` if it adds a
       distinct token bag).
    2. Send the query to XenForo's ``/api/search/`` endpoint via
       :class:`apps.sync.services.xenforo_search.XenForoSearchClient`.
       The XF Enhanced Search add-on routes that to Elasticsearch's
       BM25 ranker; without the add-on it falls back to MySQL fulltext
       (worse, but the retriever still works — operator-visible
       degradation is surfaced by the health probe).
    3. Map each hit's ``(content_id, content_type)`` to a ``ContentKey``
       and look up its sentence IDs in
       ``context.content_to_sentence_ids``. Hits whose ContentKey isn't
       in the in-memory record set (i.e. not yet imported, or excluded
       from this pipeline pass) are silently skipped.

    The retriever is feature-flagged off by default via
    ``stage1.xenforo_bm25_retriever_enabled``. When enabled alongside
    :class:`SemanticRetriever`, :func:`run_retrievers` automatically
    fuses the two ranked lists with RRF (Cormack et al. 2009).

    Why XF-source-only:
    - XF's ES index covers forum threads, posts, and resources only.
    - WordPress / blog / crawled-page hosts aren't there. For lexical
      coverage of those sources, see :class:`LexicalRetriever` and
      :class:`QueryExpansionRetriever`.

    References
    ----------
    - BM25: Robertson & Zaragoza (2009), "The Probabilistic Relevance
      Framework: BM25 and Beyond", *Foundations and Trends in IR* 3(4).
    - RRF fusion: Cormack, Clarke, Büttcher (2009), SIGIR'09 — applied
      automatically by :func:`run_retrievers` when more than one
      retriever is active.
    - XF Enhanced Search: https://xenforo.com/docs/xf2/enhanced-search/
    """

    name: str = "xenforo_bm25"

    def __init__(
        self,
        *,
        enabled: bool = False,
        client: object | None = None,
        per_dest_limit: int = 200,
        min_query_length: int = 3,
    ):
        self.enabled = enabled
        self._client = client
        self.per_dest_limit = per_dest_limit
        self.min_query_length = min_query_length

    def retrieve(self, context: RetrievalContext) -> dict[ContentKey, list[int]]:
        if not self.enabled:
            return {}
        client = self._resolve_client()
        if client is None:
            return {}

        result: dict[ContentKey, list[int]] = {}
        for dest_key in context.destination_keys:
            dest_record = context.content_records.get(dest_key)
            if dest_record is None:
                continue
            query = self._build_query(dest_record)
            if len(query) < self.min_query_length:
                continue
            hits = client.search_threads(query, limit=self.per_dest_limit)
            if not hits:
                continue

            sentence_ids: list[int] = []
            seen_hosts: set[ContentKey] = set()
            for hit in hits:
                host_key: ContentKey = (hit.content_id, hit.content_type)
                if host_key == dest_key:
                    continue
                if host_key in seen_hosts:
                    continue
                host_sentences = context.content_to_sentence_ids.get(host_key)
                if not host_sentences:
                    continue
                seen_hosts.add(host_key)
                sentence_ids.extend(host_sentences)

            if sentence_ids:
                result[dest_key] = sentence_ids
        return result

    def _resolve_client(self):
        """Lazy-construct the search client; tolerate boot/credential gaps.

        The retriever may be enabled by AppSetting before
        ``XENFORO_BASE_URL`` / ``XENFORO_API_KEY`` are configured.
        Rather than raising mid-pipeline (which would poison the run),
        we log and return ``None`` so :func:`run_retrievers` records an
        empty contribution and the SemanticRetriever path still wins.
        """
        if self._client is not None:
            return self._client
        try:
            from apps.sync.services.xenforo_search import XenForoSearchClient

            self._client = XenForoSearchClient()
        except Exception:  # noqa: BLE001 — boot/credential safety; logged for operator
            logger.warning(
                "XenForoBM25Retriever: search client unavailable "
                "(check XENFORO_BASE_URL / XENFORO_API_KEY) — skipping"
            )
            self._client = None
        return self._client

    @staticmethod
    def _build_query(record) -> str:
        """Concatenate title + distinct scope title into one query string.

        Title alone is the strongest signal; scope title (e.g. forum
        node name) adds topical context when it isn't a substring of
        the title. Empty/whitespace fields are tolerated.
        """
        title = (getattr(record, "title", "") or "").strip()
        scope = (getattr(record, "scope_title", "") or "").strip()
        if not title:
            return scope
        if not scope or scope.lower() in title.lower():
            return title
        return f"{title} {scope}"


# ── Concrete: PixieRetriever (Group A.3 / FR-021) ─────────────────


class PixieRetriever:
    """Graph-based random walk candidate retriever (Pixie algorithm).

    FR-021: Generates candidates by performing random walks on the
    Article-Entity bipartite graph. Uses the C++ extension `pixie_walk`
    for O(1) alias sampling and parallel execution.

    Group A.3: Deduplicates the persisted walks into `PixieWalkVisit`
    tuples (source, visited, count) to drastically cut disk usage
    on dense graphs, matching the Pixie visitation matrix exactly.
    """

    name: str = "pixie_walk"

    def __init__(
        self,
        *,
        enabled: bool = False,
        walk_steps_per_entity: int = 5000,
        top_k: int = 100,
        walk_length: int = 2,
    ):
        self.enabled = enabled
        self.walk_steps_per_entity = walk_steps_per_entity
        self.top_k = top_k
        self.walk_length = walk_length

    def retrieve(self, context: RetrievalContext) -> dict[ContentKey, list[int]]:
        if not self.enabled:
            return {}

        try:
            from extensions import pixie_walk
        except ImportError:
            logger.warning(
                "pixie_walk C++ extension not found. Skipping PixieRetriever."
            )
            return {}

        from apps.knowledge_graph.models import ArticleEntityEdge, PixieWalkVisit
        import numpy as np

        # Fetch the entire graph edges to build CSR
        edges = ArticleEntityEdge.objects.values_list(
            "content_item_id", "entity_id", "weight"
        )
        if not edges:
            return {}

        content_ids = list(set(e[0] for e in edges))
        entity_ids = list(set(e[1] for e in edges))

        c_to_idx = {c: i for i, c in enumerate(content_ids)}
        e_to_idx = {e: i + len(content_ids) for i, e in enumerate(entity_ids)}
        idx_to_c = {i: c for c, i in c_to_idx.items()}

        num_nodes = len(content_ids) + len(entity_ids)

        adj = [[] for _ in range(num_nodes)]
        for c, e, w in edges:
            c_idx = c_to_idx[c]
            e_idx = e_to_idx[e]
            adj[c_idx].append((e_idx, w))
            adj[e_idx].append((c_idx, w))

        indptr = np.zeros(num_nodes + 1, dtype=np.uint32)
        indices = []
        weights = []

        current_idx = 0
        for i in range(num_nodes):
            for neighbor, weight in adj[i]:
                indices.append(neighbor)
                weights.append(weight)
                current_idx += 1
            indptr[i + 1] = current_idx

        indices = np.array(indices, dtype=np.uint32)
        weights = np.array(weights, dtype=np.float32)

        result: dict[ContentKey, list[int]] = {}

        valid_dest_keys = []
        for dest_key in context.destination_keys:
            dest_pk = dest_key[0]
            if dest_pk in c_to_idx:
                valid_dest_keys.append(dest_key)

        if not valid_dest_keys:
            return {}

        # Phase 0.9 (Wave 1 A.3): atomic UPSERT instead of delete+recreate.
        # Django 5.2's ``bulk_create(..., update_conflicts=True, ...)`` maps
        # to Postgres ``INSERT ... ON CONFLICT (...) DO UPDATE`` which:
        #   * never deletes existing rows (so concurrent readers don't see
        #     a partial-empty walk graph mid-write);
        #   * lets the next walk overwrite the visit_count atomically;
        #   * removes the per-batch DELETE round-trip.
        # The previous delete+bulk_create pattern worked under last-write-
        # wins semantics but had a brief gap where readers saw zero walks
        # for a destination, and burnt one DELETE statement per refresh.
        visits_to_create = []

        for dest_key in valid_dest_keys:
            dest_pk = dest_key[0]
            q_node = np.array([c_to_idx[dest_pk]], dtype=np.uint32)
            q_weight = np.array([1.0], dtype=np.float32)

            o_nodes, o_scores, o_visits = pixie_walk.walk(
                indptr,
                indices,
                weights,
                num_nodes,
                q_node,
                q_weight,
                self.walk_steps_per_entity,
                self.top_k,
                self.walk_length,
            )

            sentence_ids = []
            for n_idx, score, visit_count in zip(o_nodes, o_scores, o_visits):
                if n_idx >= len(content_ids):
                    continue
                host_pk = idx_to_c[n_idx]
                if host_pk == dest_pk:
                    continue

                visits_to_create.append(
                    PixieWalkVisit(
                        source_content_id=dest_pk,
                        visited_content_id=host_pk,
                        visit_count=visit_count,
                        signal_version="v1",
                    )
                )

                host_key = None
                for hk in context.content_records.keys():
                    if hk[0] == host_pk:
                        host_key = hk
                        break

                if host_key:
                    sentence_ids.extend(
                        context.content_to_sentence_ids.get(host_key, [])
                    )

            if sentence_ids:
                result[dest_key] = sentence_ids

        if visits_to_create:
            PixieWalkVisit.objects.bulk_create(
                visits_to_create,
                batch_size=1000,
                update_conflicts=True,
                update_fields=["visit_count", "created_at"],
                unique_fields=["source_content", "visited_content", "signal_version"],
            )

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


# ── Concrete: TantivyBM25Retriever ───────────────────────────────


class TantivyBM25Retriever:
    """In-process BM25 keyword retriever over host titles via Tantivy.

    True Okapi BM25 (Robertson & Zaragoza 2009) without a separate
    search server: Tantivy is the approved Rust replacement for a
    Lucene-style index (docs/specs/fr-approved-library-expansion-bank.md
    § "Need full-text search without JVM"). Unlike
    :class:`XenForoBM25Retriever` it covers ALL host sources (WordPress,
    crawled — not just forum threads) and keeps working when the forum's
    search endpoint is down. Unlike :class:`LexicalRetriever` it weighs
    term rarity and document length instead of raw token overlap, so it
    produces a different rank order — added value for RRF fusion.

    The index is built fresh in RAM per pipeline pass from host title +
    scope_title (the same text the lexical retriever reads): no on-disk
    index, no staleness, no rebuild task. Feature-flagged via the
    AppSetting ``stage1.tantivy_bm25_retriever_enabled`` (default ON).
    Cold-start safe: missing package, empty corpus, or empty query all
    return ``{}``.
    """

    name: str = "tantivy_bm25"

    def __init__(self, *, enabled: bool = False):
        self.enabled = enabled

    @staticmethod
    def _index_text(record) -> str:
        """Lowercased alphanumeric text for one record.

        Lowercasing also neutralises the query parser's AND/OR/NOT
        operators (they are only operators in uppercase), and the
        character strip removes quote/paren/colon query syntax.
        """
        import re

        merged = " ".join(
            part
            for part in (
                getattr(record, "title", "") or "",
                getattr(record, "scope_title", "") or "",
            )
            if part
        )
        return re.sub(r"[^a-z0-9 ]+", " ", merged.lower()).strip()

    def _build_index(self, context: RetrievalContext):
        """Index every host record; returns (index, ordered keys) or None."""
        import tantivy  # pylint: disable=import-error

        builder = tantivy.SchemaBuilder()
        builder.add_text_field("body", stored=False)
        builder.add_unsigned_field("host_idx", stored=True)
        index = tantivy.Index(builder.build())
        # Fixed small heap: the corpus is titles only (a few MB at 100k
        # hosts), far below this commit buffer.
        writer = index.writer(heap_size=16_000_000)
        indexed_keys: list[ContentKey] = []
        for key, record in context.content_records.items():
            text = self._index_text(record)
            if not text:
                continue
            writer.add_document(tantivy.Document(body=text, host_idx=len(indexed_keys)))
            indexed_keys.append(key)
        if not indexed_keys:
            return None
        writer.commit()
        index.reload()
        return index, indexed_keys

    def retrieve(self, context: RetrievalContext) -> dict[ContentKey, list[int]]:
        if not self.enabled:
            return {}
        try:
            import tantivy  # pylint: disable=import-error  # noqa: F401
        except ImportError:
            logger.warning(
                "tantivy package not installed; tantivy_bm25 retriever "
                "contributed nothing this pass (rebuild the backend image)"
            )
            return {}

        built = self._build_index(context)
        if built is None:
            return {}
        index, indexed_keys = built
        searcher = index.searcher()

        result: dict[ContentKey, list[int]] = {}
        for dest_key in context.destination_keys:
            dest_record = context.content_records.get(dest_key)
            if dest_record is None:
                continue
            query_text = self._index_text(dest_record)
            if not query_text:
                continue
            query = index.parse_query(query_text, ["body"])
            hits = searcher.search(query, context.top_k + 1).hits
            sentence_ids: list[int] = []
            for _score, address in hits:
                host_key = indexed_keys[searcher.doc(address).get_first("host_idx")]
                if host_key == dest_key:
                    continue
                sentence_ids.extend(context.content_to_sentence_ids.get(host_key, []))
            if sentence_ids:
                result[dest_key] = sentence_ids
        return result


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
    - :class:`XenForoBM25Retriever` — flipped on by
      ``stage1.xenforo_bm25_retriever_enabled``. Calls XF Enhanced
      Search via the existing API key for true BM25 over forum
      content. Per-destination hit limit comes from
      ``stage1.xenforo_bm25_per_dest_limit`` (default 200).

    When more than one retriever is active, :func:`run_retrievers`
    automatically uses RRF (#31) to fuse the per-dest ranked lists.
    All opt-ins are independent — operators can enable any subset.
    """
    retrievers: list[CandidateRetriever] = [SemanticRetriever()]
    if _setting_enabled("stage1.lexical_retriever_enabled"):
        retrievers.append(LexicalRetriever(enabled=True))
    if _setting_enabled("stage1.query_expansion_retriever_enabled"):
        retrievers.append(QueryExpansionRetriever(enabled=True))
    if _setting_enabled("stage1.xenforo_bm25_retriever_enabled"):
        from apps.core.models import AppSetting

        per_dest_limit = AppSetting.get_int(
            "stage1.xenforo_bm25_per_dest_limit", 200
        )
        retrievers.append(
            XenForoBM25Retriever(enabled=True, per_dest_limit=per_dest_limit)
        )
    if _setting_enabled("stage1.tantivy_bm25_retriever_enabled"):
        retrievers.append(TantivyBM25Retriever(enabled=True))

    # FR-021: Graph-based Pixie Retriever
    if _setting_enabled("graph_candidate.enabled"):
        from apps.core.models import AppSetting

        walk_steps = AppSetting.get_int("graph_candidate.walk_steps_per_entity", 5000)
        top_k = AppSetting.get_int("graph_candidate.top_k_candidates", 100)

        retrievers.append(
            PixieRetriever(
                enabled=True,
                walk_steps_per_entity=walk_steps,
                top_k=top_k,
                walk_length=2,
            )
        )

    return retrievers


def _setting_enabled(key: str) -> bool:
    """Read a boolean AppSetting flag with the key's cold-start default.

    Catches every conceivable failure mode (Django not initialised,
    AppSetting model missing, DB unreachable, migration not applied,
    ``SimpleTestCase`` DatabaseOperationForbidden guard) and returns
    the key's default. Optional retrievers stay off unless the project
    has promoted that retriever to a default-on path.

    Refactor 2026-05-04: shared coerce_bool from apps.api.query_params.
    """
    from apps.api.query_params import coerce_bool

    try:
        from apps.core.models import AppSetting

        row = AppSetting.objects.filter(key=key).first()
    except Exception:  # noqa: BLE001 — cold-start / boot-order safe.
        return key in _DEFAULT_ON_SETTING_KEYS
    if row is None or not row.value:
        return key in _DEFAULT_ON_SETTING_KEYS
    return coerce_bool(row.value, default=False)
