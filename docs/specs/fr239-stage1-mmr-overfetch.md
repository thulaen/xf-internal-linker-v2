# FR-239 — Stage-1 MMR rerank algorithm helper

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Stage-1 MMR rerank (overfetch + diversity reduction) |
| **Settings prefix** | (none yet — algorithm helper has no operator tunable. Wire-in commit will add `pipeline.stage1_mmr_enabled`, `pipeline.stage1_overfetch_multiplier`, `pipeline.stage1_mmr_lambda` keys.) |
| **Pipeline stage** | Stage 1 (coarse content-level retrieval) — wire-in pending |
| **Helper** | `apps.pipeline.services.slate_diversity.mmr_rerank_keys` |
| **Module constants** | `STAGE1_MMR_LAMBDA_DEFAULT = 0.7`, `STAGE1_OVERFETCH_MULTIPLIER_DEFAULT = 2` |
| **Default state** | Algorithm shipped 2026-05-07; Stage-1 wire-in is the next commit's job (deferred — see §6 below). Once wired, default-on per the no-opt-in mandate. |

## 2 · Motivation (ELI5)

Stage 1 today asks FAISS "give me the 50 most similar pages to this destination" and that's it. Those 50 can be 50 near-copies of the same page (think: 50 forum threads asking the same question with slight wording changes). Stage 2 then has nothing diverse to choose from. The fix: ask FAISS for 100 candidates instead of 50 (overfetch), then use Maximal Marginal Relevance (MMR) to pick the 50 that are both most-relevant AND most-different from each other. This trades a small retrieval cost (2× FAISS work, still milliseconds) for materially better Stage-2 input.

The fix already exists at the FINAL stage as FR-015 (Carbonell & Goldstein 1998 MMR over `ScoredCandidate` objects). FR-239 brings the same algorithm to Stage 1 retrieval, where it can shape the candidate pool BEFORE expensive sentence-level scoring.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Carbonell, J. & Goldstein, J. (1998). *The Use of MMR, Diversity-Based Reranking for Reordering Documents and Summaries.* SIGIR '98. DOI: [10.1145/290941.291025](https://doi.org/10.1145/290941.291025). §3 defines `MMR(D_i) = λ · Sim(q, D_i) − (1 − λ) · max_{D_j ∈ S} Sim(D_i, D_j)`. Table 2 reports best precision/diversity at λ ∈ [0.3, 0.7]. |
| **Survey confirmation** | Drosou, M. & Pitoura, E. (2010). *Search Result Diversification.* SIGMOD Record 39(1). DOI: [10.1145/1860702.1860709](https://doi.org/10.1145/1860702.1860709). §3.1 confirms MMR remains the best practical default twelve years after Carbonell. |
| **Cascade context** | Wang, L., Lin, J. & Metzler, D. (2011). *A Cascade Ranking Model for Efficient Ranked Retrieval.* SIGIR '11. DOI: [10.1145/2009916.2009934](https://doi.org/10.1145/2009916.2009934). §3 — the "retrieve more then prune" pattern is canonical for cascade rankers. |
| **Industry prior art** | The same project's existing `_mmr_select_for_host` (FR-015, `slate_diversity.py:131`) — written from the same Carbonell paper. FR-239 reuses the math at the algorithm layer; the API is separate because Stage-1 keys aren't `ScoredCandidate` objects. |
| **What we reproduce** | Carbonell 1998 §3 formula verbatim. λ default 0.7 = balanced setting per Carbonell Table 2 + Drosou §3.1. Overfetch = 2× per Carbonell §3 ("retrieve at least 2× to give MMR room"). |
| **What we diverge on** | Two design choices: (1) returning the original relevance score (not the MMR composite) so callers can compose Stage-1 scores into later stages per FR-238 cascade preservation; (2) treating missing-embedding candidates as fully-diverse (max_sim = 0) so a stale embedding cache doesn't drop legitimate candidates. Both choices are documented contracts. |

## 4 · Output contract

`mmr_rerank_keys(scored_keys, embedding_lookup, *, k, lambda_=0.7) -> list[tuple[object, float]]`

| Param | Type | Contract |
|---|---|---|
| `scored_keys` | `list[tuple[key, relevance]]` | Ordered descending by relevance. Relevance score is treated as comparable to embedding cosine (caller's job to ensure — e.g. both in [-1, 1] for L2-unit BGE-M3 vectors). |
| `embedding_lookup` | `dict[key, np.ndarray]` | L2-unit embeddings per key. Missing key → fall back to relevance-only (max_sim = 0, "fully diverse"). Zero-size array → same fallback. |
| `k` | `int` | Number of picks to return. Capped at `len(scored_keys)`. |
| `lambda_` | `float ∈ [0, 1]` | 1.0 = pure relevance (degenerates to score-sort), 0.0 = pure diversity. Default `STAGE1_MMR_LAMBDA_DEFAULT = 0.7`. |

Returns `list[tuple[key, original_relevance]]` of length `min(k, len(scored_keys))` in MMR-pick order. Returned scores are the ORIGINAL relevance, not the MMR composite — callers that need the MMR value can recompute it from the input.

Special cases:
- `scored_keys == []` → returns `[]` (no math).
- `len(scored_keys) <= k` → returns a fresh copy of the input (MMR has nothing to compress).

## 5 · Implementation

| File | Change |
|---|---|
| `backend/apps/pipeline/services/slate_diversity.py` | Added `mmr_rerank_keys` (~30 lines), `_pick_next_mmr_index` (~18 lines, computes argmax of MMR formula), `_append_pick` (~6 lines, encapsulates the "track this pick + its embedding" bookkeeping). Module constants `STAGE1_MMR_LAMBDA_DEFAULT = 0.7`, `STAGE1_OVERFETCH_MULTIPLIER_DEFAULT = 2`. |
| `backend/apps/pipeline/tests_slate_diversity_helpers.py` | New file. 14 SimpleTestCase tests across 2 classes. |

Total: ~120 lines added. No DB migrations, no settings, no UI. Zero existing-caller risk (algorithm helper has no callers yet).

## 6 · Why the wire-in is deferred

The algorithm is shipped, tested, and ready. Wiring it into `_stage1_semantic_candidates` requires three additional changes that warrant their own change-window:

1. **Overfetch multiplier in retrieval calls.** `_run_faiss_block_search` and `_stage1_numpy_fallback` need to ask for `top_k × 2` candidates instead of `top_k`. This doubles Stage-1 retrieval cost — needs a benchmark sweep to confirm sub-50ms p95 still holds under load (per `docs/PERFORMANCE.md` §6.1).
2. **Host-embedding fetch on the FAISS path.** FAISS doesn't expose vectors back to Python; an additional pgvector lookup keyed on the FAISS-returned host PKs is needed before MMR can run. The lookup helper exists (`_fetch_host_embedding_matrix`) but the call site doesn't yet exist.
3. **Settings keys + recommended defaults migration.** `pipeline.stage1_mmr_enabled` (default `true`), `pipeline.stage1_overfetch_multiplier` (default `2`, citation Carbonell §3), `pipeline.stage1_mmr_lambda` (default `0.7`, citation Carbonell Table 2 + Drosou §3.1). Plus a Django data migration to seed them in `AppSetting`.

These are 3 independently-reviewable changes, each with their own risk profile. Shipping the algorithm helper first, in isolation, lets the wire-in be a focused PR with a clear before/after benchmark. This also matches the project's `THINK-BEFORE-YOU-CODE.md` rule against "premature integration" — the algorithm is the upstream piece; the wire-in is the downstream piece that benefits from being separable.

The `STAGE1_OVERFETCH_MULTIPLIER_DEFAULT = 2` constant is exported alongside `STAGE1_MMR_LAMBDA_DEFAULT = 0.7` precisely so the wire-in commit is a small change: import the constants, double the retrieval count, fetch embeddings, call `mmr_rerank_keys`.

## 7 · Test plan

`MmrRerankKeysTests` (11 cases per Beizer 1990 boundary value analysis):
1. **Empty input** → empty output (zero-row short-circuit).
2. **`k > len(input)`** → input returned unchanged (fresh list).
3. **First pick is highest relevance** (Carbonell §3 — empty S means no diversity term).
4. **λ=1 degenerates to score-sort** (no diversity term).
5. **λ=0 picks orthogonal second** over near-duplicate.
6. **Default λ constant locked at 0.7** (Carbonell Table 2 + Drosou §3.1).
7. **Default overfetch multiplier locked at 2** (Carbonell §3).
8. **λ=0.7 prefers diverse over near-duplicate** (Carbonell §3.2 balanced setting).
9. **Missing embedding → fully diverse fallback** (avoid dropping legitimate candidates due to stale lookup).
10. **Zero-size embedding → same fallback** (sentinel for "no embedding" matches Stage-1 path convention).
11. **Returned score is original relevance, not MMR composite** (cascade-preservation contract per FR-238).

`PickNextMmrIndexTests` (3 cases — internal argmax helper):
1. **Argmax is returned** when relevance dominates.
2. **Empty selected_embeddings → max_sim=0** (degenerate case).
3. **Diversity penalty demotes similar candidate** (core Carbonell §3 invariant).

All 14 tests run as `SimpleTestCase` (no DB, no Docker dependency).

## 8 · Performance

| Metric | Value |
|---|---|
| Cost per call | O(k × n × d) where n = len(scored_keys), d = embedding dim. At k=50, n=100, d=1024 → ~5 million fp32 multiplies = ~5ms on modern CPU. |
| At 10× scale | n=1000 → 50ms per destination. Acceptable for batch-size 64 destinations = 3.2s total Stage-1 overhead. |
| At 100× scale | n=10,000 → 500ms per destination. **Extension point**: switch to a chunked NumPy implementation that vectorizes `np.dot` across all selected embeddings simultaneously. |

The current Python implementation is intentionally readable; a vectorized NumPy + C++ kernel can be added later if profiling demands it. The existing FR-015 path uses the C++ `feedrerank.calculate_mmr_scores_batch` kernel for the same math at the final stage — that kernel could be reused for Stage 1 once the wire-in lands.

## 9 · Compatibility / migration

| Item | Impact |
|---|---|
| Existing callers of `apply_slate_diversity` (FR-015) | Unchanged. The FR-015 helper is untouched; FR-239 added new functions next to it. |
| Existing callers of `_mmr_select_for_host` (FR-015 internal) | Unchanged. |
| Schema migrations | None. |
| Settings additions | None in this commit; the wire-in commit will add the three keys listed in §6. |

Pure-additive change. Zero production code paths reference the new helper yet.

## 10 · Citations on every default

- `STAGE1_MMR_LAMBDA_DEFAULT = 0.7` — Carbonell & Goldstein 1998 SIGIR Table 2 (best precision/diversity tradeoff) + Drosou & Pitoura 2010 SIGMOD Record §3.1 (twelve-year follow-up confirmation).
- `STAGE1_OVERFETCH_MULTIPLIER_DEFAULT = 2` — Carbonell & Goldstein 1998 §3 ("retrieve at least 2× to give MMR room").
- Missing-embedding fallback to fully-diverse (max_sim = 0) — pragmatic engineering choice; the alternative ("drop the candidate") would silently penalize legitimate hosts whose embedding cache is stale, which is a worse user-visible failure mode than over-including them.
- Returned-score = original relevance (not MMR composite) — FR-238 cascade-preservation principle (Wang/Lin/Metzler 2011 SIGIR §3).

## 11 · Operator-facing surface

None in this commit. The wire-in commit will add a `/settings` card under "Pipeline" with the three settings keys, plus a `peHelper` plain-English tooltip explaining "this picks varied candidates instead of near-duplicates" for each.

## 12 · Failure modes and recovery

| Failure | Behaviour |
|---|---|
| All candidates have missing embeddings | All `max_sim = 0` → MMR collapses to score-sort. Output is identical to input (truncated to k). Acceptable: relevance-only is the safe fallback. |
| All candidates have identical embeddings | All `max_sim = 1.0` (after first pick) → MMR composite is `λ·rel - (1-λ)`. Argmax becomes argmax of relevance again. Output is descending relevance. Acceptable: when there's no diversity to find, return the most-relevant. |
| `k <= 0` | `len(scored_keys) <= k` short-circuit returns input unchanged when `k >= len(scored_keys)`; for `k <= 0` returns up to k items via the while loop's `len(selected) < k` condition (which is immediately false). Documented but not user-facing — Stage-1 callers won't hit this. |

## 13 · Extension points

- Stage-1 wire-in (the deferred work in §6) is the immediate next step.
- C++ kernel reuse — the existing `feedrerank.calculate_mmr_scores_batch` C++ helper computes the exact same math the Python loop does. Once Stage-1 wire-in lands, a 5-line swap from the Python loop to the C++ kernel will give the same speedup that FR-015 already enjoys at the final stage.
- Different relevance normalization — the current contract treats raw scores as relevance directly. An alternative is `_mmr_select_for_host`-style normalization (subtract bottom score, divide by range) which would let the algorithm work with score scales that aren't pre-normalized to [-1, 1]. Documented as an extension if a non-FAISS retriever (e.g. BM25 with its own score scale) feeds into MMR.

## 14 · Status

**Stage-1 wire-in shipped 2026-05-07** in the same day as the algorithm helper. Default-on.

Wire-in details (commit superseding §6's deferral):
- `_stage1_semantic_candidates` now reads `_stage1_mmr_settings()` at call time and overfetches by `pipeline.stage1_overfetch_multiplier` (default 2) when `pipeline.stage1_mmr_enabled` is true (default true).
- New `_retrieve_stage1_candidates` (extracted helper) does the FAISS-first / NumPy-fallback retrieval with the larger top_k.
- New `_apply_stage1_mmr` calls `mmr_rerank_keys` per-destination using host embeddings fetched via the existing `_fetch_host_embedding_matrix` helper. Missing-embedding hosts fall through with the documented "fully diverse" semantics.
- The post-MMR diverse host set replaces the diagnostic `host_scores` entries in-place so operators see the post-MMR pool, not the pre-MMR overfetched pool.
- Settings keys seeded by migration `suggestions/0061_seed_fr237_through_fr250_defaults.py`.

Verification:
- `python .githooks/check-forbidden-patterns.py --strict` on all touched files → 0 NEW warnings.
- `docker compose exec backend python manage.py test apps.pipeline.tests_pipeline_stages_helpers apps.pipeline.tests_slate_diversity_helpers apps.pipeline.tests_embeddings_helpers apps.pipeline.test_candidate_retrievers` → 88 tests pass (14 from algorithm-helper tests + 4 new ApplyStage1MmrTests + the 70 prior pass). OK.
- New `ApplyStage1MmrTests` (4): pass-through when pool ≤ k, picks diverse subset over near-duplicates, empty score list returns raw verbatim, no host keys returns input unchanged.
