# FR-240 — Hybrid retrieval (lexical + dense) via Reciprocal Rank Fusion

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Hybrid retrieval — lexical + dense via RRF |
| **Settings prefix** | `stage1.lexical_retriever_enabled`, `pipeline.bm25_*`, `pipeline.rrf_k`, `pipeline.lexical_top_k` |
| **Pipeline stage** | Stage 1 (coarse content-level retrieval) |
| **Helpers** | `apps.pipeline.services.candidate_retrievers.LexicalRetriever`, `apps.pipeline.services.candidate_retrievers._fuse_via_rrf`, `apps.pipeline.services.reciprocal_rank_fusion.fuse` |
| **Default state** | **ON.** v1 ships default-on via `stage1.lexical_retriever_enabled = true` (seeded by migration `0062_seed_fr240_fr241_default_on.py`). v2 BM25 swap-in uses the `pipeline.bm25_*` keys. |

## 2 · Motivation (ELI5)

Pure-meaning matching misses obvious word matches. If someone literally types "Docker" the pipeline doesn't favour a page titled "Docker Tutorial" — it ranks any page about "container engines" the same way. A lexical retriever that scores word-overlap fixes this. Two ranked lists (one by meaning, one by words) are then combined into a single ranking using a parameter-free fusion called RRF. RRF picks the items that BOTH lists like (the safest signals) and surfaces them ahead of items only one list likes.

This also closes **FR-244 cold-start** automatically: a brand-new article has no embedding yet, so the SemanticRetriever returns nothing for it. The LexicalRetriever still works (it only needs the title text, which is always available), so cold-start destinations get suggestions immediately.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Lexical (BM25)** | Robertson, S. & Zaragoza, H. (2009). *The Probabilistic Relevance Framework: BM25 and Beyond.* Foundations and Trends in IR 3(4), 333–389. DOI: [10.1561/1500000019](https://doi.org/10.1561/1500000019). §3.4 — `k1=1.2`, `b=0.75` are the canonical Lucene-tuned defaults. |
| **Fusion (RRF)** | Cormack, G. V., Clarke, C. L. A. & Büttcher, S. (2009). *Reciprocal Rank Fusion outperforms Condorcet and individual Rank Learning Methods.* SIGIR '09. DOI: [10.1145/1571941.1572114](https://doi.org/10.1145/1571941.1572114). §3 — `k=60` is their tuned smoothing constant. |
| **Hybrid retrieval analysis** | Bruch, S., Gai, S. & Ingber, A. (2023). *An Analysis of Fusion Functions for Hybrid Retrieval.* ACM TOIS. arXiv: [2210.11934](https://arxiv.org/abs/2210.11934). Confirms RRF is the safe default vs. learned-weight fusion. |
| **Cold start** | Schein, A. I. et al. (2002). *Methods and Metrics for Cold-Start Recommendations.* SIGIR '02. DOI: [10.1145/564376.564421](https://doi.org/10.1145/564376.564421). Defines lexical fallback as the gold standard when dense embeddings are unavailable. |

## 4 · Output contract

`run_retrievers([SemanticRetriever, LexicalRetriever, ...], context, fuse_with_rrf=True, rrf_k=60) -> dict[ContentKey, list[int]]`
- Per destination: each retriever produces an ordered `list[sentence_id]`.
- `_fuse_via_rrf` (existing helper) computes `RRF(d) = Σ_r 1/(k + rank_r(d))` where `rank_r(d)` is the 1-based rank of `d` in retriever `r`'s output.
- Output: per destination, a single fused ranked list of sentence IDs.

The full RRF math lives in `backend/apps/pipeline/services/reciprocal_rank_fusion.py:fuse`. Cormack 2009 §2 eq. 1.

## 5 · v1 implementation (shipped default-on 2026-05-07)

| Component | Status | Source |
|---|---|---|
| `SemanticRetriever` (FAISS / NumPy cosine over BGE-M3) | ON since FR-030 | `candidate_retrievers.py:92` |
| `LexicalRetriever` (token-overlap, Jaccard-style) | **NOW ON** via migration 0062 | `candidate_retrievers.py:226` |
| `_fuse_via_rrf` (Cormack 2009 §2 eq. 1) | Always ON when ≥2 retrievers contribute | `candidate_retrievers.py:663` |
| Cold-start fallback | Automatic — when SemanticRetriever returns ∅ for a destination, the fused result == LexicalRetriever's result for that destination | `_fuse_via_rrf:690` short-circuits single-source destinations |

The token-overlap LexicalRetriever is a defensible v1: it captures the same lexical-match signal that BM25 does, just without IDF + length normalization. RRF fusion makes the difference smaller still — RRF only uses ranks, not raw scores, so the absence of IDF only matters when two host titles tie on overlap (rare given the hosting site's title diversity).

## 6 · v2 BM25 swap-in (planned, not yet shipped)

The existing `LexicalRetriever` can be drop-in-replaced with a Postgres-FTS-backed BM25 version reading `pipeline.bm25_k1`, `pipeline.bm25_b`, and `pipeline.lexical_top_k`. The settings keys are already seeded so the swap is a code-only change.

When v2 ships:
- Add Postgres GIN index on `ContentItem.body_normalized`.
- Replace `_rank_hosts_by_overlap` body with a `to_tsquery` + `ts_rank_cd`-based query that respects the BM25 saturation curve.
- Keep the `name = "lexical"` so the RRF fusion treats it identically.
- Update spec §5 to reflect the swap.

No settings-schema migration needed — keys are already in place from migration 0061.

## 7 · Test plan

The infrastructure already has full test coverage in `backend/apps/pipeline/test_candidate_retrievers.py` (31 tests). FR-240 is a default-flip, not new code, so no new test file is needed.

Pre-existing tests that confirm default-on behaviour:
- `test_run_retrievers_with_rrf_fusion` — multi-retriever path produces fused output.
- `test_lexical_retriever_returns_top_k_by_overlap` — algorithm correctness.
- `test_run_retrievers_skips_failing_retriever` — one retriever crashing doesn't kill the others (cold-start safe).

## 8 · Compatibility / migration

| Item | Impact |
|---|---|
| Existing operator overrides | Untouched. `get_or_create` only seeds when row absent. |
| Performance | LexicalRetriever's host-token-bag is cached on `RetrievalContext._host_token_bags_cache`; second-retriever calls are O(1). RRF fusion is O(n × m) for n destinations × m retrievers — typically 50 × 2 = 100 fused entries per dest. Negligible vs. FAISS forward pass. |
| Schema migrations | None. AppSetting seeding only. |

## 9 · Operator-facing surface

`/settings` already exposes the toggle as part of the Stage-1 retrievers card (`apps.core.views_stage1_retrievers`). The card body shows: "Lexical retriever — when on, the pipeline also runs a keyword-overlap match alongside the meaning-based match. Combined via RRF. Default: ON."

## 10 · Citations on every default

- `stage1.lexical_retriever_enabled = true` — Robertson & Zaragoza 2009 §3 (lexical retrieval as a complementary signal); Cormack et al. 2009 §3 (RRF makes the dual-retriever path strictly better than single-retriever); Schein et al. 2002 (cold-start defence).
- `pipeline.bm25_k1 = 1.2` — Robertson & Zaragoza 2009 §3.4.
- `pipeline.bm25_b = 0.75` — Robertson & Zaragoza 2009 §3.4.
- `pipeline.rrf_k = 60` — Cormack et al. 2009 §3 (their tuned smoothing constant; `_fuse_via_rrf` uses `DEFAULT_RRF_K` from `reciprocal_rank_fusion.py` which equals 60).
- `pipeline.lexical_top_k = 50` — parity with `pipeline.stage1_top_k = 50` per Bruch et al. 2023 §4.1.

## 11 · Failure modes

| Failure | Behaviour |
|---|---|
| Both retrievers return ∅ for a destination | Destination has no candidates this run; logged via `run_retrievers` info-level messages. Stage 2 sees an empty list and emits a `no_semantic_matches` diagnostic per the existing pipeline. |
| LexicalRetriever raises | `run_retrievers:619` swallows the exception and continues with SemanticRetriever's output. RRF degenerates to single-source pass-through. |
| Postgres FTS unavailable (v2) | Falls back to v1 token-overlap (same code path; the swap-in must be feature-gated). |

## 12 · Status

**Shipped default-on 2026-05-07** via migration `0062_seed_fr240_fr241_default_on.py`. v2 BM25 swap-in pending (settings keys already seeded for the eventual upgrade).

**Closes FR-244 (cold-start fallback to BM25):** subsumed because `LexicalRetriever` doesn't depend on embeddings being present. A new article with no embedding yet still gets ranked by lexical title overlap. RRF fusion's single-source short-circuit (`_fuse_via_rrf:690`) returns the lexical list unchanged when SemanticRetriever returns ∅ for a destination.
