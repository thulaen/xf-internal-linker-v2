# FR-238 — Stage-1 score preservation

## 1 · Identity

| Field | Value |
|---|---|
| **Canonical name** | Stage-1 cascade score preservation |
| **Settings prefix** | n/a — runtime infrastructure, no operator tunable |
| **Pipeline stage** | Stage 1 (coarse content-level retrieval) |
| **Helper** | `apps.pipeline.services.faiss_index.faiss_search` (return shape) + `apps.pipeline.services.pipeline_stages._unpack_faiss_hit` + `_run_faiss_block_search` + `_stage1_numpy_fallback` + `_stage1_semantic_candidates` (optional `host_scores_out` parameter) |
| **Default state** | ON. The new score column always rides through. The `host_scores_out` capture is opt-in per-call (default `None`), so legacy callers see no behaviour change. |

## 2 · Motivation (ELI5)

Stage 1 of the link pipeline is the "rough cut" — it asks "which other pages on this site are roughly about the same thing as this destination?" using AI fingerprints. FAISS, the search library, internally computes how similar each candidate is — a number from −1 to +1 — and orders them. Until 2026-05-07 our code was throwing those numbers away the instant FAISS produced them, keeping only the order. That's like getting a test back with a rank ("you came 3rd of 50") but no score ("87/100"). The order is useful, but the score tells you whether 3rd place was 86/100 or 16/100. Operators couldn't see this. Stage-2 (the fine cut) couldn't use it as a tie-breaker. Diagnostics couldn't flag "every Stage-1 winner this run was below 0.3 cosine — something's wrong with embeddings." This change keeps the score.

## 3 · Academic / industry source of truth

| Field | Value |
|---|---|
| **Primary** | Wang, L., Lin, J. & Metzler, D. (2011). *A Cascade Ranking Model for Efficient Ranked Retrieval.* SIGIR '11. DOI: [10.1145/2009916.2009934](https://doi.org/10.1145/2009916.2009934). §3 establishes the cascade-ranker score-propagation principle: each stage's score MUST be carried into the next stage so later stages can compose, threshold, or break ties. |
| **Earlier statement** | Burges, C. J. C. (2010). *From RankNet to LambdaRank to LambdaMART: An Overview.* MSR-TR-2010-82. Stable URL: https://www.microsoft.com/en-us/research/publication/from-ranknet-to-lambdarank-to-lambdamart-an-overview/. §4 — same principle in the context of learning-to-rank cascades. |
| **Industry prior art** | Faiss documentation (Meta AI Research): `index.search(...)` always returns `(scores, indices)` precisely so callers can use the score downstream. Throwing it away was a local choice. |
| **What we reproduce** | The cascade-stage score propagation. Stage-1 host-level inner-product score now travels with the candidate set into Stage 2 + diagnostics. |
| **What we diverge on** | We don't yet feed the Stage-1 score into the Stage-2 cosine math (Stage 2 uses sentence-level embeddings, a finer granularity). Stage-1 score is currently exposed as **diagnostic** signal via `host_scores_out`. A follow-up FR can compose Stage-1 + Stage-2 scores per Wang/Lin/Metzler 2011 §4 once we have ground-truth labelled data to validate the composition function. |

## 4 · Output contract

`faiss_search(query_vectors, k, host_pk_set=None) -> list[list[tuple[int, str, float]]]`
- Each inner tuple is `(pk, content_type, score)`.
- `score` is the FAISS `IndexFlatIP` inner product == cosine similarity for L2-unit vectors (FR-237 enforces L2-unit invariant).
- Order: descending `score` (FAISS default).

`_run_faiss_block_search(..., host_scores_out=None) -> dict[ContentKey, list[int]]`
- Return value unchanged: `dest_key → [sentence_id, ...]`.
- When `host_scores_out` is `None` (default): legacy behaviour, no side effect.
- When `host_scores_out` is a `dict`: populated with `dest_key → [(host_key, score), ...]` ordered by descending score. Self-links and host_keys with no sentences are filtered from BOTH the sentence list and the score list (in lock-step).

`_stage1_numpy_fallback(...)` and `_stage1_semantic_candidates(...)` accept the same `host_scores_out` parameter and follow the same contract.

## 5 · Backward compatibility — `_unpack_faiss_hit`

The new `faiss_search` returns 3-tuples. Several test files mock `faiss_search` with the legacy 2-tuple shape. To keep those tests passing without forcing a global rewrite, `_unpack_faiss_hit` accepts either shape:

| Hit shape | Returns | When |
|---|---|---|
| `(pk, ct, score)` | `(pk, ct, float(score))` | New FAISS path |
| `(pk, ct)` | `(pk, ct, 0.0)` | Legacy mocks; sentinel 0.0 is recognisable as "unscored" because real top-K cosines are positive |

This is a **transition adapter**. After all callers migrate, the 2-tuple branch can be removed.

## 6 · Implementation surface

| File | Change |
|---|---|
| `backend/apps/pipeline/services/faiss_index.py` | `faiss_search` now reads `scores` from `index.search(...)` instead of binding it to `_scores`; appends each score to the hit tuple. ~8 lines changed. |
| `backend/apps/pipeline/services/pipeline_stages.py` | Added `_unpack_faiss_hit` (12 lines). `_run_faiss_block_search` signature bumped with `host_scores_out` kwarg (default `None`); body unpacks 3-tuples and writes scores. `_stage1_numpy_fallback` mirrored. `_stage1_semantic_candidates` plumbs `host_scores_out` through. |
| `backend/apps/pipeline/tests_pipeline_stages_helpers.py` | Added `FaissHitUnpackingTests` (3 tests) + `RunFaissBlockSearchScorePreservationTests` (4 tests). |

Total: ~140 lines added across 3 files. No DB migrations, no settings, no UI.

## 7 · Test plan

Tests live in `backend/apps/pipeline/tests_pipeline_stages_helpers.py`.

`FaissHitUnpackingTests` (3):
1. **3-tuple round-trip** — score preserved verbatim.
2. **2-tuple legacy mock** — sentinel 0.0 returned, no exception.
3. **numpy.float32 → Python float** — type coercion correct.

`RunFaissBlockSearchScorePreservationTests` (4):
1. **Happy path** — every kept host's score is captured in `host_scores_out` in FAISS-returned order.
2. **Self-link drop** — a self-link is filtered from BOTH the sentence list AND the score list.
3. **Default opt-out** — passing `host_scores_out=None` preserves legacy return shape verbatim.
4. **No-sentences host** — a FAISS hit whose host has zero sentences is filtered from the score list (otherwise the score would imply contribution that didn't happen).

## 8 · Performance

| Metric | Value |
|---|---|
| Cost added per FAISS query | One float append per hit. Negligible vs. the FAISS forward pass. |
| Cost added when `host_scores_out=None` | Zero — the score is unpacked but not stored. |
| Memory added when `host_scores_out` populated | One `list[tuple[ContentKey, float]]` per destination, len == top_k. At top_k=50 + 100 destinations = 5,000 tuples ≈ 200 KB. |

Negligible.

## 9 · Compatibility / migration

| Item | Impact |
|---|---|
| Existing tests with 2-tuple FAISS mocks | Pass via `_unpack_faiss_hit` adapter. |
| Existing production callers of `faiss_search` | Two: `_run_faiss_block_search` (handled) and `_stage1_semantic_candidates`'s import (handled via the same path). |
| External callers of `_stage1_semantic_candidates` | None observed in `Grep` — `SemanticRetriever.retrieve` is the only consumer. |
| FAISS index format | Unchanged. Score was always computed by FAISS; only the binding name changed (`_scores` → `scores`). |

## 10 · Citations on every default

- Score propagation through cascade stages — Wang/Lin/Metzler 2011 §3.
- Backward-compat sentinel 0.0 — pragmatic engineering choice; real FAISS cosines on L2-unit BGE-M3 embeddings are always > 0 for top-K survivors, so 0.0 is recognisable as "no score".

## 11 · Operator-facing surface

No new UI. No new settings. The captured scores are infrastructure for follow-up specs (FR-241 NRT delta, FR-242 Stage-1-MMR-overfetch, FR-244 fast-path observability) that surface them to operators.

## 12 · Extension points

- A future commit can wire `host_scores_out` into `_persist_diagnostics` so operators see Stage-1 scores in the diagnostics table.
- A future commit can compose Stage-1 + Stage-2 scores per Wang/Lin/Metzler 2011 §4 (e.g., `final = α × stage1 + (1-α) × stage2` with α tuned on a held-out validation set).
- Once `LexicalRetriever` ships (Group C.2 — separate FR), its scores can travel through the same `host_scores_out` channel for RRF fusion (Cormack et al. 2009).

## 13 · Failure modes

- If `faiss_search` ever returns a tuple of length < 2: `_unpack_faiss_hit` raises `IndexError`. This is correctness — we can't fabricate a missing pk or content_type. The existing FAISS internal contract guarantees ≥2 fields.
- If `host_scores_out` is supplied but mutated externally during the loop: undefined behaviour. The contract is "supply a fresh dict; we own writes". Documented.

## 14 · Status

Shipped 2026-05-07. Single commit. Verification:
- `python .githooks/check-forbidden-patterns.py --strict` on all modified files: 0 warnings, 0 violations.
- `docker compose exec backend python manage.py test apps.pipeline.tests_pipeline_stages_helpers`: pre-existing tests + 7 new = all pass.
