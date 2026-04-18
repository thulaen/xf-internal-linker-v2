# FR-015 - Final Slate Diversity Reranking

## Confirmation

- **Active phase confirmed**: `Phase 18 / FR-015 - Final Slate Diversity Reranking` is the next target in `AI-CONTEXT.md`.
- **Backlog confirmed**: `FR-015` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No diversity reranking layer exists today. The pipeline scores and ranks candidates, applies hard constraints (FR-014 cluster suppression, FR-013 explore/exploit reranking), and then picks the top-N. There is no final step that checks whether the selected slate is diverse.

## Current Repo Map

### Ranking Assembly
- `backend/apps/pipeline/services/ranker.py`
  - Defines `ScoredCandidate` with `score_final` and all individual sub-scores.
  - Applies all weighted scoring layers (semantic, keyword, authority, freshness, phrase, anchor corroboration, rare-term, field-aware, click-distance).
  - FR-014 cluster suppression and FR-013 explore/exploit adjustments are applied here.
- `backend/apps/pipeline/services/pipeline.py`
  - Orchestrates the 3-stage pipeline.
  - Final stage currently resolves host-reuse and circularity, then takes the top-3 by `score_final`.
  - The top-3 selection is the gap FR-015 fills: it does not account for whether those 3 candidates are semantically redundant with each other.
- `backend/apps/content/models.py`
  - `ContentItem.embedding`: 1024-dimensional semantic vector (BAAI/bge-m3). Used for similarity computation.
- `backend/apps/suggestions/models.py`
  - `Suggestion` stores all per-suggestion scores and diagnostics.

### Hard Constraints Already Enforced (FR-015 must not undo these)
- FR-014 near-duplicate clustering: suppresses non-canonical cluster members.
- FR-013 explore/exploit reranking: adjusts `score_final` based on scope-pair feedback.
- Pipeline guardrails: maximum 3 suggestions per host thread; no circular links; no existing-link repeats.

## Plain-English Summary

Simple version first.

Imagine the linker finds 10 candidate destinations for a thread. All 10 have been scored and the top 3 look like this:
- #1: A guide to "Setting up Redis on Linux" — score 0.91
- #2: A guide to "Installing Redis on Ubuntu" — score 0.90
- #3: A guide to "Redis installation walkthrough" — score 0.89

These are three slightly different versions of the same topic. Linking to all three from the same thread gives the reader redundant choices and wastes all three link slots.

FR-015 adds a final check: before committing to the top-3, look at how similar they are to each other. If two candidates are nearly identical in meaning, swap in the next-best candidate that covers something different.

The result: the selected slate is both good (high scores) and varied (different topics).

## Source Summary

### Patent US20070294225A1
**Title:** "Diversifying Search Results for Improved Search and Personalization"
**Inventors:** Radlinski, Dumais, Horvitz (Microsoft)
**Published:** December 2007

Core approach: enforce diversity as a constraint on categories and dimensions **after** hard business rules and **before** (or simultaneously with) personalized reranking. The patent does not prescribe a single formula — it describes capping how many results come from any single category so the top-k set spans multiple intents. This is the architectural model: diversity as a post-constraint, pre-presentation pass.

Source: https://patents.google.com/patent/US20070294225A1/en

### Maximal Marginal Relevance (MMR)
**Paper:** Carbonell & Goldstein, SIGIR 1998 — "The Use of MMR, Diversity-Based Reranking for Reordering Documents and Producing Summaries"

MMR is the canonical algorithm for post-scoring diversity reranking. It was designed specifically to reorder an already-scored candidate list by penalizing candidates that are similar to items already selected. It is model-agnostic, requires no retraining, and operates in O(N·k) time — well suited to k=3 final-slate selection over a candidate pool of typical size.

Source: https://www.cs.cmu.edu/~jgc/publication/The_Use_MMR_Diversity_Based_LTMIR_1998.pdf

### Determinantal Point Processes (DPP) — Reference Only
**Paper:** Kulesza & Taskar (2012); YouTube/Wilhelm CIKM 2018

DPP is the mathematically principled alternative to MMR. It models the probability of a diverse high-quality subset as proportional to the determinant of a kernel matrix. In production it is used at Google (YouTube) and Pinterest. However, for k=3 final-slate selection over a small per-host candidate pool, DPP's additional complexity is not justified. MMR is chosen here because:
- The candidate pool per host thread is small (typically 10–50 after hard constraints).
- k=3 means the greedy selection only runs 3 iterations.
- MMR's λ parameter is easy to tune and explain.
- DPP requires building and factorizing a similarity kernel matrix, which is overkill for this scale.

DPP is documented here as a known future upgrade path if the pipeline ever needs to scale to larger candidate pools.

Source (YouTube DPP): https://jgillenw.com/cikm2018.pdf
Source (Fast Greedy MAP): https://arxiv.org/abs/1709.05135

## Math-Fidelity Note

### The MMR Formula

```
MMR_score(Dᵢ) = λ · Sim(Dᵢ, host)  −  (1 − λ) · max_Dⱼ∈S [ Sim(Dᵢ, Dⱼ) ]
```

Every symbol explained:

| Symbol | Meaning |
|---|---|
| Dᵢ | A candidate not yet selected, from the remaining pool R\S |
| S | The set of candidates already chosen for the slate so far |
| R\S | All remaining candidates (total pool minus already-selected) |
| Sim(Dᵢ, host) | Relevance of candidate Dᵢ — we use the normalized `score_final` from the ranker |
| Sim(Dᵢ, Dⱼ) | Cosine similarity between embeddings of Dᵢ and already-selected Dⱼ |
| max Dⱼ∈S | The penalty: the highest similarity to any already-selected item |
| λ | Diversity trade-off knob, range [0.0, 1.0] |

### How λ works

| λ value | Effect |
|---|---|
| 1.0 | Pure relevance — identical to current top-N selection, no diversity effect |
| 0.7 | Recommended default (Carbonell & Goldstein, 1998) — relevance-leaning but diversity-aware |
| 0.5 | Equal balance — strong diversity effect |
| 0.0 | Pure diversity — relevance ignored entirely (not appropriate here) |

Default: **λ = 0.7**.

### The Greedy Algorithm (Iterative)

```
Input:
  candidates     = list of ScoredCandidate objects, ordered by score_final descending
    embeddings     = dict mapping content_item_id -> 1024-dim embedding vector
  k              = max_suggestions_per_host (3)
  λ              = diversity_lambda (default 0.7)
  score_window   = max score gap between top candidate and any eligible candidate (default 0.30)
  similarity_cap = cosine similarity above which a candidate is considered "too similar" for diagnostics (default 0.90)

Step 1 — Filter to score window:
  top_score = candidates[0].score_final
  eligible  = [c for c in candidates if (top_score - c.score_final) <= score_window]

Step 2 — Greedy MMR selection:
  S = []                          (selected slate, starts empty)
  while len(S) < k and eligible is not empty:
      if S is empty:
          pick = candidate with highest score_final in eligible  (no diversity penalty yet)
      else:
          for each Dᵢ in eligible:
              relevance  = (Dᵢ.score_final - min_score) / (max_score - min_score)  # normalize to [0,1]
              max_sim    = max(cosine(embed(Dᵢ), embed(Dⱼ)) for Dⱼ in S)
              mmr_score  = λ * relevance  −  (1 − λ) * max_sim
          pick = Dᵢ with highest mmr_score
      add pick to S
      remove pick from eligible

Output: S (ordered list of selected ScoredCandidate objects)
```

### Cosine Similarity

```
cosine(u, v) = (u · v) / (‖u‖ · ‖v‖)
```

Computed between the 1024-dim BAAI/bge-m3 embedding vectors stored in `ContentItem.embedding`. Vectors are pre-normalized at write time so this reduces to a dot product. Use `numpy.dot` or pgvector's `<=>` distance operator (where cosine_similarity = 1 - distance).

### Score Window

Only candidates whose `score_final` falls within `score_window` of the top candidate are eligible for MMR selection. Candidates below this threshold stay in their original ranked position if there are not enough above-threshold candidates to fill the slate. This prevents the diversity algorithm from promoting low-quality items purely for variety.

```
eligible = {Dᵢ : score_final(top) − score_final(Dᵢ) ≤ score_window}
```

Default `score_window = 0.30`. If fewer than k candidates fall in the window, fill remaining slots with the next-highest ranked candidates regardless of the window.

## Problem Definition

The ranker today picks the top-3 candidates by `score_final`. That score encodes semantic relevance, keyword overlap, authority, freshness, phrase matching, anchor corroboration, rare-term propagation, field-aware relevance, click-distance, and explore/exploit feedback. It does not encode anything about how similar the top-3 are to **each other**.

If the top candidates are semantically near-identical (common when a site has several pages on the same sub-topic), the reviewer sees three nearly-redundant link suggestions for the same thread. This wastes review attention and results in a page with three links that all point to the same topic.

FR-015 adds a final diversity pass that swaps in more varied candidates before committing the slate.

## Hard Scope Boundaries

FR-015 must stay separate from:

| Feature | Boundary |
|---|---|
| **FR-014 (Near-Duplicate Clustering)** | FR-014 suppresses redundant *versions of the same page*. FR-015 diversifies across *different topics*. A canonical item from FR-014 can still be penalized by FR-015 if it is semantically similar to another canonical item in the slate. |
| **FR-013 (Explore/Exploit Reranking)** | FR-013 adjusts `score_final` based on scope-pair feedback. FR-015 runs **after** FR-013 adjustments are already baked into `score_final`. FR-015 uses that adjusted score as its relevance input. |
| **FR-012 (Click-Distance Prior)** | FR-012 is a scoring input. It does not change how FR-015 selects the final slate. |
| **Pipeline hard constraints** | FR-015 must never select a candidate that has been hard-suppressed (e.g., an existing link, a circular link, or a hard-blocked cross-silo candidate). Only candidates that survived the hard-constraint filter are eligible for FR-015. |

## Implementation Details

### 1. Database Changes

Add to `Suggestion`:

```python
score_slate_diversity: FloatField(null=True, blank=True)
# The MMR score used for final slot selection. Null if diversity reranking was disabled
# or if this was the first pick (no diversity penalty applied).

slate_diversity_diagnostics: JSONField(default=dict)
# Example:
# {
#   "mmr_applied": true,
#   "lambda": 0.7,
#   "score_window": 0.30,
#   "slot": 1,
#   "relevance_normalized": 0.88,
#   "max_similarity_to_selected": 0.43,
#   "mmr_score": 0.54,
#   "swapped_from_rank": null,   # null if this was already top-ranked
#   "algorithm_version": "fr015-v1"
# }
```

### 2. Service Logic (`SlateDiversityService`)

File: `backend/apps/pipeline/services/slate_diversity.py`

```
class SlateDiversityService:

    def rerank(self, candidates, embeddings, settings) -> list[ScoredCandidate]:
        """
        Takes the post-constraint ranked candidates for a single host thread.
        Returns the final ordered slate using MMR greedy selection.

        candidates : list of ScoredCandidate, sorted by score_final descending
        embeddings : dict of {content_item_id: np.ndarray (1024-dim, pre-normalized)}
        settings   : SlateDiversitySettings namedtuple
        """
```

Key implementation rules:
- Only run when `settings.enabled` is True. When disabled, return candidates unchanged and set `score_slate_diversity = None`.
- Normalize relevance scores within the eligible window before applying MMR, so λ applies consistently regardless of absolute score magnitudes.
- The first selected item gets `score_slate_diversity = score_final` (no penalty — it is the baseline).
- Subsequent items get the computed `mmr_score`.
- Write diagnostics for every slot, including whether a swap occurred.
- Never modify `score_final` in place. The MMR score is stored separately in `score_slate_diversity`. Downstream code uses `score_slate_diversity` for final slot ordering when diversity is enabled.
- If fewer than 2 eligible candidates exist, no diversity swap is possible. Return unchanged and log in diagnostics.

### 3. Pipeline Integration

In `pipeline.py`, after FR-013 reranking and after hard-constraint filtering, call:

```python
if slate_diversity_settings.enabled:
    ranked_candidates = slate_diversity_service.rerank(
        candidates=ranked_candidates,
        embeddings=embedding_lookup,
        settings=slate_diversity_settings,
    )
```

This must be the **last** reranking step before the top-k candidates are committed as suggestions. Order of pipeline steps:

```
1. Score all candidates (ranker.py — FR-006 through FR-014 weights)
2. Apply hard constraints (existing-link blocks, circular-link blocks, cross-silo hard blocks)
3. Apply FR-013 explore/exploit adjustment (already baked into score_final)
4. Apply FR-014 cluster suppression (already baked into score_final)
5. [NEW] FR-015 MMR diversity selection ← insert here
6. Take top-k = 3 from FR-015 output
7. Resolve host-reuse guardrail (max 3 links per host thread — already enforced)
8. Write Suggestion rows
```

### 4. Settings

Settings API endpoint: `GET/PUT /api/settings/slate-diversity/`

Fields:

| Field | Type | Default | Range | Notes |
|---|---|---|---|---|
| `enabled` | Boolean | True | — | Master switch. When False, slate selection is unchanged from current behavior. |
| `diversity_lambda` | Float | 0.7 | 0.0 – 1.0 | MMR λ. Lower = more diversity. 1.0 = no effect (pure relevance). |
| `score_window` | Float | 0.30 | 0.05 – 1.0 | Max score gap from top candidate. Only candidates within this window are eligible for diversity reranking. |
| `similarity_cap` | Float | 0.90 | 0.70 – 0.99 | Cosine similarity above which two items are considered "near-duplicate" for diagnostics and warnings. Does not block selection — that is FR-014's job. Used for explainability only. |
| `algorithm_version` | String | "fr015-v1" | — | Read-only. Version stamp written into diagnostics for pipeline reproducibility. |

AppSetting keys: `slate_diversity.enabled`, `slate_diversity.diversity_lambda`, `slate_diversity.score_window`, `slate_diversity.similarity_cap`, `slate_diversity.algorithm_version`.

### 5. Angular Settings Card

Add a "Slate Diversity Reranking" card to the Settings page, consistent with existing FR settings cards.

Controls:
- Enable/disable toggle
- λ slider (0.0–1.0, step 0.05, labeled "Relevance ↔ Diversity")
- Score window input (0.05–1.0, step 0.05)
- Tooltip descriptions for all controls

### 6. Review Diagnostics

In the Suggestion detail panel (review page), add a "Slate Diversity" section showing:
- Whether MMR was applied to this slot
- The slot number (1, 2, or 3)
- The λ value used
- The relevance (normalized `score_final`) used as input
- The max cosine similarity to already-selected items in the same slate
- The final MMR score
- Whether this item was a swap (i.e., it was not originally in the top slot)

### 7. Admin Exposure

In the `Suggestion` admin detail view, add `score_slate_diversity` and `slate_diversity_diagnostics` as read-only fields.

## API Surface

| Endpoint | Method | Description |
|---|---|---|
| `/api/settings/slate-diversity/` | GET | Read current slate diversity settings |
| `/api/settings/slate-diversity/` | PUT | Update slate diversity settings |

No recalculation endpoint is needed. Unlike clustering or PageRank, slate diversity is applied during each pipeline run — it is not a pre-computed field that needs a separate background task. To see the effect, re-run the pipeline.

## Test Plan

### 1. Math Unit Tests (`tests/pipeline/test_slate_diversity.py`)

- **Lambda = 1.0 (pure relevance)**: assert the output order is identical to the input order regardless of embedding similarity.
- **Lambda = 0.0 (pure diversity)**: assert the second selected item has the lowest cosine similarity to the first, not the second-highest score.
- **Neutral when disabled**: when `enabled=False`, assert `score_slate_diversity` is null and candidates are unchanged.
- **First slot has no penalty**: assert `score_slate_diversity` for slot 1 equals its normalized relevance (no max_sim term).
- **Score window enforced**: if candidate #4 is outside the score window, assert it is never selected even if it would maximize MMR.
- **Score window fallback**: if only 2 candidates are in the window but k=3, assert the third slot is filled from outside the window without error.

### 2. Swap Detection Test

- Create 5 candidates with scores [0.90, 0.89, 0.88, 0.85, 0.80].
- Set embeddings so candidates 1, 2, 3 are near-identical (cosine > 0.95) and candidate 4 is different (cosine < 0.30 to all others).
- Run MMR with λ=0.7.
- Assert candidate 4 is selected over candidate 3 despite its lower score.
- Assert `swapped_from_rank` in diagnostics for that slot is not null.

### 3. Hard-Constraint Respect

- Mark candidate #2 as hard-suppressed (e.g., existing link).
- Assert it never appears in the MMR output regardless of λ.

### 4. Pipeline Integration Test

- Run a full pipeline against test content where the top candidates are semantically near-duplicate.
- Assert the resulting `Suggestion` rows have `score_slate_diversity` populated.
- Assert `slate_diversity_diagnostics` contains `mmr_applied: true`.
- Assert `algorithm_version` in diagnostics equals `"fr015-v1"`.

### 5. Parity Test (Disabled)

- Run the pipeline with `slate_diversity.enabled = False`.
- Assert that `Suggestion` ordering matches the pre-FR-015 behavior (sorted by `score_final` only).

## Non-Goals

FR-015 does not:
- Change `score_final` in place. MMR produces a separate `score_slate_diversity` field.
- Apply diversity across different host threads. Each host thread has its own independent MMR pass.
- Override hard constraint suppression from FR-014 or the pipeline.
- Replace FR-014 (near-duplicate clustering). FR-014 suppresses near-duplicate *versions* of a page. FR-015 diversifies across *topics*.
- Implement DPP (saved as a documented future upgrade path).
- Run as a background task. It runs inline during each pipeline execution.
