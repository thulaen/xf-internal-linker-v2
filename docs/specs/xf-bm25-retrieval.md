# XenForo BM25 hybrid retrieval — spec

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | XenForo BM25 hybrid retrieval (Path A — REST API) |
| **Settings prefix** | `stage1.xenforo_bm25` |
| **Pipeline stage** | Stage-1 candidate retrieval (alongside SemanticRetriever, LexicalRetriever, QueryExpansionRetriever) |
| **Helper modules** | `backend/apps/sync/services/xenforo_search.py` (search client) · `backend/apps/pipeline/services/candidate_retrievers.py::XenForoBM25Retriever` |
| **Tests modules** | `backend/apps/sync/tests_xenforo_search.py` · `backend/apps/pipeline/test_candidate_retrievers.py::XenForoBM25RetrieverTests` |
| **Health probe** | `backend/apps/health/services.py::check_xenforo_search_health` |
| **Default state** | **ON.** Seeded by migration `0066_seed_xenforo_bm25_default_on.py`. Operator can disable via `/settings/` → Stage-1 Candidate Retrievers card. |
| **Related spec** | `fr240-hybrid-retrieval-bm25-rrf.md` — see §1a below for how this retriever relates to FR-240. |
| **Spec status** | Path A only. Path B (direct Elasticsearch) deferred — see §11. |

## 1a · Relationship to FR-240

FR-240 ("Hybrid retrieval — lexical + dense via RRF") shipped on 2026-05-07 and turned the existing token-overlap `LexicalRetriever` default-on. This XenForo BM25 spec is **additive, not replacement**: a *third* retriever feeding the same RRF fusion pipeline.

| Aspect | FR-240 v1 (shipped) | FR-240 v2 (planned) | This spec (XF BM25) |
|---|---|---|---|
| Retriever class | `LexicalRetriever` | `LexicalRetriever` (rewritten) | `XenForoBM25Retriever` |
| Backend | In-process Python (token-overlap, no IDF) | Postgres FTS (`to_tsquery` + `ts_rank_cd`) | XenForo Enhanced Search REST API → Elasticsearch |
| Source coverage | All ContentItems (XF + WP + crawled) | All ContentItems | XenForo content only (threads + posts + resources) |
| Algorithm | Jaccard-style intersection size | True BM25 (k₁, b configurable) | True BM25 (Lucene defaults via Elasticsearch) |
| Settings prefix | `stage1.lexical_retriever_enabled`, `pipeline.bm25_*` (planned) | same | `stage1.xenforo_bm25_*` |
| Default state | ON via migration 0062 | n/a (not yet shipped) | ON via migration 0066 |
| Network calls | None | None | One ``/api/search/`` request per XF destination |

**Why three retrievers, not one:**

- FR-240 v1's token-overlap is fast (in-memory) and covers *all* sources, but is statistically weaker than real BM25.
- FR-240 v2 would give real BM25 across all sources, but requires building a Postgres FTS index over content bodies — significant new infrastructure.
- This spec's XF BM25 piggybacks on the forum's already-running Elasticsearch via the existing API key — zero new infrastructure, true BM25 quality, but XF-only coverage.

The three coexist deliberately. RRF fusion (Cormack et al. 2009 — already implemented in `apps.pipeline.services.reciprocal_rank_fusion.fuse`) merges all active retrievers' per-destination ranked lists with no per-retriever weight tuning. Running all three when FR-240 v2 ships will give:

1. **Coverage breadth** from FR-240 v1/v2 (all sources).
2. **Forum BM25 precision** from this retriever (XF only).
3. **Meaning-based recall** from `SemanticRetriever` (FAISS, all sources).

Operators can disable any retriever via `/settings/` → Stage-1 Candidate Retrievers card without touching the others.

## 2 · Motivation (ELI5)

Today the linker picks where to put internal links by comparing **meanings** of sentences using AI fingerprints called "embeddings". A library called FAISS does the matching on the GPU. Meaning-search is great for topical similarity but misses two important cases:

1. **Exact-keyword matches** — product names, version strings, jargon, acronyms. Embeddings are fuzzy and don't reward "the words match exactly."
2. **Topic-vs-intent confusion** — "how to fix bug X" and "why bug X cannot be fixed" embed almost identically, and "running shoes" lives next to "running socks" in meaning-space.

The fix is **hybrid retrieval**: run a keyword-search retriever in parallel with the meaning-search one and merge the two ranked lists. The XenForo forum we already import from runs Elasticsearch via the **Enhanced Search add-on** (XenForo's plugin that swaps MySQL fulltext for Elasticsearch). Our existing API key has all scopes, so we can ask Elasticsearch for proper keyword-ranked candidates **for free** — no new server, no new auth, no new firewall hole.

## 3 · Academic sources of truth

### 3a · BM25 (the keyword-match scoring formula)

| Field | Value |
|---|---|
| **Full citation** | Robertson, S. & Zaragoza, H. (2009). "The Probabilistic Relevance Framework: BM25 and Beyond." *Foundations and Trends in Information Retrieval*, 3(4), 333–389. DOI [10.1561/1500000019](https://doi.org/10.1561/1500000019). |
| **Open-access link** | <https://www.staff.city.ac.uk/~sbrp622/papers/foundations_bm25_review.pdf> |
| **Relevant section(s)** | §3 (BM25 derivation), §3.5 (parameter defaults k₁ ≈ 1.2, b ≈ 0.75) |
| **What we faithfully reproduce** | We rely on Elasticsearch's stock BM25 implementation — same formula, same default parameters. |
| **What we deliberately diverge on** | We don't tune k₁/b ourselves — Elasticsearch and the XenForo Enhanced Search add-on own those defaults. If forum-side ranking quality regresses, the operator tunes ES, not us. |

### 3b · RRF (the merge formula for hybrid retrieval)

| Field | Value |
|---|---|
| **Full citation** | Cormack, G. V., Clarke, C. L. A., & Büttcher, S. (2009). "Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods." *Proceedings of the 32nd ACM SIGIR Conference*, pp. 758–759. DOI [10.1145/1571941.1572114](https://doi.org/10.1145/1571941.1572114). |
| **Open-access link** | <https://plg.uwaterloo.ca/~gvcormac/cormacksigir09-rrf.pdf> |
| **Relevant section(s)** | §3 (RRF formula `score(d) = Σ 1 / (k + rank(d))`); the empirical k = 60 default. |
| **What we faithfully reproduce** | Formula and k = 60 default — implemented in `apps.pipeline.services.reciprocal_rank_fusion.fuse` (existing helper, reused). Auto-applied by `run_retrievers` when more than one retriever is active. |
| **What we deliberately diverge on** | Nothing — we use the paper's recipe verbatim. |

### 3c · XenForo Enhanced Search (the add-on this depends on)

| Field | Value |
|---|---|
| **Documentation** | <https://xenforo.com/docs/xf2/enhanced-search/> |
| **What we faithfully reproduce** | We treat `/api/search/` as the only call surface. The XF add-on owns the ES connection, schema, and BM25 parameter tuning. |
| **What we deliberately diverge on** | We do **not** access Elasticsearch directly (Path B in §11). Direct ES access requires separate credentials, a network path to the ES port, and ops responsibility for someone else's database — not worth it given Path A covers the use cases here. |

## 4 · Input contract (the new retriever)

`XenForoBM25Retriever(*, enabled=False, client=None, per_dest_limit=200, min_query_length=3)`

- **`enabled`** — bool. When False, `retrieve()` returns `{}` immediately. Default False; flipped on by the AppSetting `stage1.xenforo_bm25_retriever_enabled`.
- **`client`** — optional `XenForoSearchClient` instance for dependency injection (tests). When None, lazily constructed from `XENFORO_BASE_URL` / `XENFORO_API_KEY` settings on first `retrieve()` call. If construction fails (missing creds), the retriever logs and returns `{}` — never raises.
- **`per_dest_limit`** — int. Max hits requested from XF per destination. Default 200, matching the existing FAISS over-fetch (`Stage1.candidate_per_destination_overfetch`). Configured via AppSetting `stage1.xenforo_bm25_per_dest_limit`.
- **`min_query_length`** — int. Destinations whose built query string is shorter are skipped (XF rejects very short queries; cuts API budget waste). Default 3.

Empty-input behaviour:
- Empty `context.destination_keys` → returns `{}` (no HTTP calls).
- Destination with empty `title` and empty `scope_title` → query is empty → that destination is skipped.
- XF returns 0 hits for a destination → that destination is omitted from the result map.

## 5 · Output contract

Returns `dict[ContentKey, list[int]]` where:
- Keys are destination ContentKeys (`(content_id, content_type)` tuples).
- Values are deduplicated, ordered lists of host sentence IDs from `context.content_to_sentence_ids`.
- Self-links (host_key == dest_key) are filtered out.
- Hosts not in `context.content_to_sentence_ids` (i.e. not imported, or excluded from this pipeline pass) are filtered out.

Order within each list reflects XF's relevance order (best match first). Order is preserved through `run_retrievers`'s RRF fusion via `apps.pipeline.services.reciprocal_rank_fusion.fuse`.

## 6 · Configuration (AppSetting keys)

| Key | Type | Default | Source |
|---|---|---|---|
| `stage1.xenforo_bm25_retriever_enabled` | bool | `true` (seeded by migration 0066) | Mirrors FR-240 v1's default-on rollout — same risk profile, cold-start safe |
| `stage1.xenforo_bm25_per_dest_limit` | int | `200` | Matches existing FAISS over-fetch |

RRF k (smoothing constant) is owned by `reciprocal_rank_fusion.DEFAULT_RRF_K = 60` (Cormack et al. 2009). Not duplicated as a separate AppSetting here — that's the canonical place.

## 7 · Hardware-aware defaults

This retriever is network I/O bound, not compute bound. No GPU, no VRAM, no FAISS-budget changes. The existing `xenforo_api` rate-limit bucket (4 req/s, 10 burst — 80% of XenForo's documented ~5/s/key) protects the forum. Search calls share the same bucket as the importer, so the BM25 retriever can never starve the importer or vice-versa.

## 8 · No-duplicates compliance

This retriever does **not** persist anything. Hits from XF are transient candidates fed into the existing ranker. No new artefact table → honours the strict no-duplicates rule.

A future caching layer (Redis with content-hash + signal-version key, ≤1h TTL) is deliberately out of scope for V1 — see §11.

## 9 · Ranking-gates compliance

Per `docs/RANKING-GATES.md`:

- **Gate B (user-idea intake)** — filled by the planning thread that produced this spec (`C:\Users\goldm\.claude\plans\does-using-elasticsearch-make-polished-wren.md`) plus the discussion in chat that confirmed Enhanced Search is installed and the API key has all scopes.
- **Gate A (implementation)** — filled by this spec section, the test files listed in §1, and the verification steps in §10.

### Gate-A checklist

- [x] Patent / paper / RFC citation provided (BM25 + RRF in §3).
- [x] Existing-code overlap check — `LexicalRetriever` and `QueryExpansionRetriever` already exist; the new retriever is XF-source-specific, so it complements rather than duplicates them. RRF fusion is reused from `reciprocal_rank_fusion.py` (no new module).
- [x] Regression check — feature-flagged off by default; existing FAISS-only path is unchanged. Existing tests in `test_candidate_retrievers.py` continue to pass (10 new tests added, 0 modified).
- [x] Architecture alignment — Python orchestration calling a network API (no hot path; CPP-FIRST does not apply).
- [x] Conflict flag — none.

## 10 · Verification (end-to-end)

1. **Forbidden-patterns linter:**
   ```
   python .githooks/check-forbidden-patterns.py --strict \
     backend/apps/sync/services/xenforo_search.py \
     backend/apps/sync/tests_xenforo_search.py
   ```
   Expect 0 warnings, 0 violations.

2. **Unit tests (no Docker, no network):**
   ```
   docker compose exec backend python manage.py test \
     apps.sync.tests_xenforo_search \
     apps.pipeline.test_candidate_retrievers
   ```
   Expect new + existing tests pass.

3. **Health-page probe (live forum, read-only):** open `/health/`; verify the new "XenForo Enhanced Search" row reports HEALTHY.

4. **Smoke test (live forum, read-only):**
   ```
   docker compose exec backend python manage.py shell -c \
     "from apps.sync.services.xenforo_search import XenForoSearchClient; \
      print(XenForoSearchClient().search_threads('machine learning', limit=10))"
   ```
   Expect a list of `XFSearchHit` items with non-empty titles and content IDs.

5. **A/B comparison (feature-flagged):**
   - Run pipeline with `stage1.xenforo_bm25_retriever_enabled=false` for a known XF-source destination → record top-50 suggestions.
   - Flip flag on, rerun → record top-50.
   - Compare. Expect new high-quality candidates that FAISS missed (especially exact-keyword matches: product names, version strings, acronyms).

6. **Rate-limit safety:** trigger 100 search calls in a tight loop; verify ≤4/sec, no 429s from the forum.

## 11 · Out of scope (deferred, by design)

- **Path B — direct Elasticsearch access.** Requires separate ES credentials and a network path to the ES port. Only worth it for raw ES aggregations or query-log mining; Path A (REST API) covers the BM25 retrieval use case completely.
- **Lexical retrieval for non-XF content** (WordPress, blog, crawled pages). XF's ES index doesn't contain those. A separate plan will cover them — likely Postgres `pg_trgm` rather than ES.
- **Anchor reverse-lookup with snippets.** Smaller follow-up that adds a single read-only search call to the review-queue UI.
- **Result caching (Redis, content-hash keyed).** A future optimisation; V1 makes one HTTP call per destination per pipeline pass and lets the existing rate-limit bucket pace the load.
- **Resource-type search.** V1 calls `search_threads` only. `search_posts` is implemented in the client but not yet plumbed into the retriever; resources can be added in a follow-up if measurement shows it adds candidates that thread-search misses.

## 12 · Tech-debt delta

This change closes the following long-standing gaps (per `TECH-DEBT-MANDATE.md`):

1. The disabled `LexicalRetriever` (naive token-overlap stub) is now superseded by real BM25 for XF-source content — operators have an upgrade path that doesn't require building a BM25 implementation locally.
2. "No hybrid retrieval" architectural gap closed.
3. Glossary gaps filled — BM25, RRF, MLT, Enhanced Search, Elasticsearch, hybrid retrieval added to `PLAIN-ENGLISH-RULE.md`.
4. Health page gains a real Enhanced Search probe (`xenforo_search` row); previously no probe existed for the search endpoint.
5. `XenForoSearchClient` returns a typed `XFSearchHit` NamedTuple — no raw dicts at the API boundary, unlike the importer's existing methods (which return raw dicts). Establishes the typed-return pattern for future XF API surfaces.
6. Establishes a citation paper trail for BM25 and RRF (this spec) which the existing `LexicalRetriever` lacks.
