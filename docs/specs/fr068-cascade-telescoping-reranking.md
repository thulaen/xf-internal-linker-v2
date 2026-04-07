# FR-068 - Cascade Telescoping Re-Ranking

## Confirmation

- **Backlog confirmed**: `FR-068 - Cascade Telescoping Re-Ranking` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No multi-stage ranking architecture exists in the current system. All 16+ ranking signals currently compute for ALL candidates in a single pass. FR-068 introduces a 3-stage cascading architecture where cheap signals filter broadly, medium-cost signals refine, and expensive signals apply only to the final shortlist -- reducing total compute by 3-5x while maintaining top-10 quality.
- **Repo confirmed**: The existing C++ extensions pattern in `backend/extensions/` supports the small neural network forward passes needed for `cascade.cpp`. Each stage's network is a tiny 2-layer MLP with ~50 features and 32-64 hidden units.

## Current Repo Map

### Single-stage pipeline already available

- `backend/apps/pipeline/services/ranker.py`
  - `rank(...)` -- computes ALL signals for ALL candidates, then sorts.
  - For 10,000 candidates, every signal fires on every candidate -- including expensive ones like embedding similarity, learned anchor, and feedback UCB.

- `backend/apps/pipeline/services/pipeline.py`
  - Orchestrates the full pipeline. No concept of "stages" or "progressive narrowing."
  - All candidates enter the ranker and all signals compute.

### Signal cost hierarchy (observed)

Cheap signals (< 1ms per candidate):
- `score_keyword` (Jaccard set intersection)
- `score_click_distance` (integer comparison)
- `scope_proximity` (silo path comparison)
- `readability_match` (float comparison)
- `boilerplate_ratio` (float comparison)

Medium-cost signals (1-10ms per candidate):
- `score_field_bm25` (BM25 computation across fields)
- `score_phrase_match` (phrase lookup)
- `long_click_ratio` (GA4 data lookup)
- `content_update_magnitude` (token set comparison)

Expensive signals (10-100ms per candidate):
- `score_semantic` (embedding cosine similarity via FAISS)
- `score_feedback_ucb` (bandit score with history lookup)
- `learned_anchor` (model inference)
- All social/engagement signals (database queries)
- Topic purity, information gain, etc.

### Training data already available

- `backend/apps/suggestions/models.py`
  - Editor-labelled suggestions with feature vectors.
  - Each stage's training uses "pruned training sets" -- only items that would have reached that stage under the current cascade configuration.

## Source Summary

### Patent: US7689615B2 -- Ranking Results Using Multiple Nested Ranking (Microsoft, 2010)

**Plain-English description of the patent:**

The patent describes applying ranking models in a telescoping cascade: an initial cheap model scores all candidates, then progressively more expensive models re-rank shrinking subsets. Each stage uses a model specifically trained for its position in the cascade (trained on items that survived to that stage, not on the full candidate set). This "pruned training" ensures each model specialises in the distinctions relevant to its tier.

**Repo-safe reading:**

The patent uses deep neural networks per stage. This repo uses tiny 2-layer MLPs (32-64 hidden units) since the feature space is modest (~50 features total) and the goal is speed, not model capacity. The cascade control logic is simple: score, sort, truncate, pass to next stage.

**What is directly supported by the patent:**

- multi-stage cascading with progressive candidate narrowing;
- per-stage model training on pruned training sets;
- increasing model complexity and feature richness at each stage.

**What is adapted for this repo:**

- 3 stages (all -> 200 -> 50 -> 10) instead of arbitrary depth;
- tiny MLPs instead of deep networks;
- feature sets organised by signal compute cost (cheap -> medium -> expensive);
- pairwise margin loss for training each stage;
- C++ extension for fast neural network forward passes.

## Plain-English Summary

Simple version first.

Imagine you are hiring for one job and you receive 10,000 resumes. You would not give every resume a 1-hour deep review. Instead:

1. **Stage 1 (30 seconds each)**: skim all 10,000 resumes for basic qualifications (right degree, right experience level). Keep the top 200.
2. **Stage 2 (5 minutes each)**: read those 200 more carefully for relevant skills and projects. Keep the top 50.
3. **Stage 3 (30 minutes each)**: deeply evaluate those 50 against the full job criteria. Pick the top 10.

This is exactly what FR-068 does for link ranking:

1. **Stage 1**: score all N candidates using only cheap signals (keyword match, scope proximity, boilerplate ratio). Keep the top 200. Total work: N cheap evaluations.
2. **Stage 2**: re-score 200 candidates using cheap + medium signals (BM25, phrase match, engagement). Keep the top 50. Total work: 200 medium evaluations.
3. **Stage 3**: re-score 50 candidates using ALL signals (embeddings, feedback UCB, social signals, topic purity, everything). Return the top 10. Total work: 50 expensive evaluations.

Without cascade: N candidates x all signals = enormous compute.
With cascade: N cheap + 200 medium + 50 expensive = much less compute.

For N=10,000 candidates, this reduces total signal computation by roughly 3-5x while the top 10 results stay identical (because all signals still fire on the top 50).

## Problem Statement

The current single-stage pipeline computes all ranking signals for all candidates. This has two problems:

1. **Wasted compute**: expensive signals (embedding similarity, feedback UCB, learned anchor) compute for thousands of candidates that will never reach the top 10. Over 95% of this computation is thrown away.
2. **Scaling ceiling**: as more signals are added (FR-038 through FR-090+), the per-candidate cost increases linearly. The single-stage architecture means every new signal multiplies against every candidate.

FR-068 solves both by introducing a cascading architecture where expensive signals only compute for small candidate sets, and new signals can be added to Stage 3 without affecting Stage 1/2 performance.

## Goals

FR-068 should:

- implement a 3-stage cascade: all -> top 200 -> top 50 -> top 10;
- assign signals to stages based on compute cost (cheap/medium/expensive);
- train a small neural network per stage on pruned training sets;
- use pairwise margin loss for each stage's training;
- implement neural network forward passes in C++ (`cascade.cpp`);
- reduce total ranking compute by 3-5x on typical workloads;
- maintain identical top-10 quality compared to single-stage (verified by NDCG@10);
- keep the cascade off by default until operator validates quality;
- fit within ~30 MB RAM (3 tiny networks + feature buffers).

## Non-Goals

FR-068 does not:

- add new ranking signals -- it re-organises when existing signals compute;
- modify any individual signal computation;
- use deep learning (the MLPs are tiny: 2 layers, 32-64 hidden units);
- require GPU (CPU inference is sufficient for the network sizes);
- replace any other meta-algorithm (it is an architectural pattern, not a scoring model);
- change the final ranking output format -- the top 10 are still Suggestion objects with all scores;
- implement production code in the spec pass.

## Math-Fidelity Note

### Stage architecture

```text
Stage 1 -- ALL N candidates, cheap features only:
  F_1 = {keyword_jaccard, scope_proximity, boilerplate_ratio, readability_match}
  Net_1: Linear(|F_1|, 32) -> ReLU -> Linear(32, 1)
  Keep top N_1 = min(200, N)

Stage 2 -- top N_1, medium features added:
  F_2 = F_1 UNION {BM25_score, phrase_match, long_click_ratio, content_update_magnitude}
  Net_2: Linear(|F_2|, 32) -> ReLU -> Linear(32, 1)
  Keep top N_2 = min(50, N_1)

Stage 3 -- top N_2, all features:
  F_3 = F_2 UNION {embedding_sim, feedback_ucb, all social signals, topic_purity, ...}
  Net_3: Linear(|F_3|, 64) -> ReLU -> Linear(64, 1)
  Return top N_3 = 10
```

### Neural network forward pass

For a single stage with input dimension `d_in`, hidden dimension `h`, and `n` candidates:

```text
Input: X in R^{n x d_in}     [feature matrix]
       W_1 in R^{d_in x h}   [first layer weights]
       b_1 in R^h             [first layer bias]
       W_2 in R^{h x 1}      [second layer weights]
       b_2 in R^1             [second layer bias]

Hidden: H = ReLU(X * W_1 + b_1)     [n x h]
Output: S = H * W_2 + b_2           [n x 1, scores]
```

### Training per stage

Each stage is trained on a "pruned training set" -- only items that would have reached that stage:

```text
For Stage k:
  Pruned set = { items that survived Stage 1 through Stage k-1 }
  This ensures the model learns to distinguish among items of similar quality
  (the hard cases at each tier), not waste capacity on obvious rejects.
```

**Pairwise margin loss:**

```text
L = SUM_{(u,v) : u is better} max(0, 1 - (score(u) - score(v)))
```

where "u is better" means u has a higher editorial label than v.

**Optimiser:**

```text
Adam with learning_rate = 0.001, batch_size = 128
```

### Compute savings analysis

```text
Single-stage cost (baseline):
  C_single = N * (C_cheap + C_medium + C_expensive)

Cascade cost:
  C_cascade = N * C_cheap + N_1 * C_medium + N_2 * C_expensive
            = N * C_cheap + 200 * C_medium + 50 * C_expensive

Savings ratio for N = 10,000:
  C_cheap << C_medium << C_expensive, so:
  C_single ~ N * C_expensive = 10000 * C_expensive
  C_cascade ~ 50 * C_expensive + small terms
  Savings ~ 200x on expensive signals
  Overall savings ~ 3-5x (accounting for cheap/medium stages)
```

### C++ extension signature

```text
cascade.cpp:
  void stage_score(
    const float* features,   // n x d feature matrix (row-major)
    int n,                   // number of candidates
    int d,                   // feature dimension for this stage
    const float* W1,         // d x h weight matrix
    const float* b1,         // h bias vector
    int h,                   // hidden dimension
    const float* W2,         // h x 1 weight matrix
    const float* b2,         // 1 bias scalar
    float* scores_out        // n scores (output)
  )
```

### RAM budget

```text
Stage 1 net: |F_1| * 32 + 32 + 32 * 1 + 1 = ~161 floats ~ 644 bytes
Stage 2 net: |F_2| * 32 + 32 + 32 * 1 + 1 = ~321 floats ~ 1.3 KB
Stage 3 net: |F_3| * 64 + 64 + 64 * 1 + 1 = ~3265 floats ~ 13 KB

Total network weights: ~15 KB
Feature buffers per stage: n * d * 4 bytes ~ 200 * 50 * 4 = 40 KB
Total: ~30 MB with all overhead, training workspace, and batch buffers
```

## Scope Boundary Versus Existing Signals

FR-068 must stay separate from:

- `Single-stage pipeline (ranker.py)`
  - the current pipeline computes all signals for all candidates;
  - FR-068 organises the same signals into a staged cascade;
  - same signals, different execution architecture.

- `All individual signals`
  - FR-068 does not modify how any signal is computed;
  - it only controls WHEN each signal computes (which stage);
  - signal computations are unchanged.

- `ListNet (FR-060) / SmoothRank (FR-066) / Rank Aggregation (FR-067)`
  - these meta-algorithms optimise scoring functions;
  - FR-068 optimises the scoring ARCHITECTURE (when to apply which model);
  - orthogonal concerns.

- `RRF (FR-046)`
  - RRF fuses rankings from multiple sources at a single stage;
  - FR-068 cascades stages with increasing feature richness;
  - different architectural pattern.

Hard rule: FR-068 must not modify any signal computation. It controls which signals compute at which stage and manages the progressive narrowing of candidate sets.

## Inputs Required

FR-068 uses only data already available:

- All `score_*` fields on `Suggestion` -- feature vectors for network training
- `Suggestion.status` -- editorial labels for training
- `Suggestion.pipeline_run_id` -- batch grouping
- Signal compute cost classification (cheap/medium/expensive) -- configured by operator

Explicitly disallowed inputs:

- raw text, embeddings, or analytics data directly
- any data not derivable from existing pipeline computations

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `cascade.enabled`
- `cascade.stage1_keep`
- `cascade.stage2_keep`
- `cascade.stage3_return`
- `cascade.stage1_features`
- `cascade.stage2_features`
- `cascade.retrain_interval_days`
- `cascade.min_training_items`

Defaults:

- `enabled = false` (off by default -- significant architectural change)
- `stage1_keep = 200`
- `stage2_keep = 50`
- `stage3_return = 10`
- `stage1_features = ["keyword_jaccard", "scope_proximity", "boilerplate_ratio", "readability_match"]`
- `stage2_features = ["bm25_score", "phrase_match", "long_click_ratio", "content_update_magnitude"]`
- `retrain_interval_days = 7`
- `min_training_items = 200`

Bounds:

- `50 <= stage1_keep <= 1000`
- `10 <= stage2_keep <= 200`
- `5 <= stage3_return <= 50`
- `stage1_keep > stage2_keep > stage3_return` (enforced)
- `50 <= min_training_items <= 2000`

### Feature-flag behavior

- `enabled = false`
  - use the single-stage pipeline as today
  - no cascade overhead
- `enabled = true`
  - switch to 3-stage cascade
  - compute diagnostics comparing cascade top-10 vs. single-stage top-10
  - log compute savings

## Diagnostics And Explainability Plan

Add one new diagnostics object per pipeline run:

- `PipelineRun.cascade_diagnostics`

Required fields:

- `cascade_state` -- `active`, `disabled`, `fallback_single_stage`
- `stage1_input_count` -- total candidates entering Stage 1
- `stage1_output_count` -- candidates surviving to Stage 2
- `stage2_output_count` -- candidates surviving to Stage 3
- `stage3_output_count` -- final candidates returned
- `compute_time_stage1_ms` -- wall clock time for Stage 1
- `compute_time_stage2_ms` -- wall clock time for Stage 2
- `compute_time_stage3_ms` -- wall clock time for Stage 3
- `compute_time_single_stage_ms` -- estimated time if single-stage had been used (for comparison)
- `compute_savings_ratio` -- `single_stage_ms / cascade_total_ms`
- `top10_agreement` -- how many of cascade top-10 match single-stage top-10 (0-10)
- `ndcg_at_10_cascade` -- NDCG@10 of cascade output
- `ndcg_at_10_single` -- NDCG@10 of single-stage output (computed on a sample for comparison)
- `stage_model_versions` -- timestamp per stage's model

Per-suggestion diagnostics (for top-N_2 candidates that reach Stage 3):

- `stage1_score` -- Stage 1 model score
- `stage1_rank` -- rank after Stage 1
- `stage2_score` -- Stage 2 model score
- `stage2_rank` -- rank after Stage 2
- `stage3_score` -- Stage 3 model score (only for items reaching Stage 3)

Plain-English review helper text should say:

- `Cascade re-ranking applies cheap signals first to narrow candidates, then adds expensive signals only for the shortlist.`
- `Compute savings ratio shows how much faster the cascade is versus scoring everything.`
- `Top-10 agreement shows whether the cascade produces the same final ranking as the full pipeline.`

## Storage / Model / API Impact

### PipelineRun model

Add:

- `cascade_diagnostics: JSONField(default=dict, blank=True)`

### Per-suggestion staging scores

Add to `Suggestion` (only populated when cascade is active):

- `cascade_stage_scores: JSONField(default=dict, blank=True)` -- stores per-stage scores and ranks

### Model file storage

- 3 neural network model files in `backend/ml_models/cascade/`
  - `stage1_net.pt`, `stage2_net.pt`, `stage3_net.pt`
  - Total size: < 100 KB (tiny networks)

### C++ extension

- `backend/extensions/cascade.cpp` -- new C++ pybind11 extension
- Follows existing build pattern in `backend/extensions/CMakeLists.txt`

### Backend API

Add:

- `GET /api/settings/cascade/`
- `PUT /api/settings/cascade/`
- `POST /api/settings/cascade/retrain/` -- triggers manual retraining of all 3 stage models
- `GET /api/settings/cascade/diagnostics/` -- returns latest pipeline run cascade diagnostics

### Review / admin / frontend

Add one settings card:

- enabled toggle (with prominent "experimental" warning)
- stage keep counts (200/50/10 sliders)
- feature assignment per stage (drag-and-drop or multi-select)
- retrain interval
- manual retrain button
- compute savings chart (cascade vs. single-stage timing)
- top-10 agreement indicator
- per-stage timing breakdown

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/extensions/cascade.cpp` -- new C++ extension
- `backend/extensions/CMakeLists.txt` -- add cascade build target
- `backend/apps/pipeline/services/cascade_reranker.py` -- new service file (stage orchestration)
- `backend/apps/pipeline/services/ranker.py` -- add cascade entry point
- `backend/apps/pipeline/services/pipeline.py` -- orchestrate cascade vs. single-stage
- `backend/apps/pipeline/tasks.py` -- add periodic training task for all 3 stage models
- `backend/apps/suggestions/models.py` -- add `cascade_stage_scores` field
- `backend/apps/suggestions/serializers.py` -- expose cascade diagnostics
- `backend/apps/suggestions/views.py` -- snapshot FR-068 settings
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` -- add settings and diagnostics endpoints
- `backend/apps/api/urls.py` -- wire new endpoints
- `backend/apps/pipeline/tests.py` -- FR-068 unit tests
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched:

- All individual signal computation files (signals compute the same way; cascade only controls when)
- `backend/apps/content/models.py`
- `backend/apps/graph/models.py`

## Test Plan

### 1. Stage truncation

- Stage 1 with 10,000 candidates keeps exactly top 200 (or all if fewer than 200)
- Stage 2 with 200 candidates keeps exactly top 50
- Stage 3 with 50 candidates returns top 10
- candidates are sorted by each stage's model score before truncation

### 2. Feature set progression

- Stage 1 only receives cheap features (no expensive signal columns)
- Stage 2 receives cheap + medium features
- Stage 3 receives all features

### 3. Pruned training sets

- Stage 2's training set contains only items that survived Stage 1
- Stage 3's training set contains only items that survived Stage 2
- pruned training sets are smaller than the full training set

### 4. Neural network forward pass

- each stage's network produces valid float scores for all candidates
- C++ forward pass matches Python (PyTorch) forward pass within tolerance (1e-5)

### 5. Quality preservation

- top-10 agreement between cascade and single-stage is >= 8/10 on validation data
- NDCG@10 of cascade is within 5% of single-stage NDCG@10

### 6. Compute savings

- cascade total compute time < single-stage compute time on the same input
- savings ratio >= 2.0x for candidate sets > 1,000

### 7. Fallback behaviour

- `enabled = false` -> single-stage pipeline runs as before
- model files missing -> fallback to single-stage with warning

### 8. Diagnostics coverage

- all per-stage timing, counts, and agreement metrics are recorded
- `PipelineRun.cascade_diagnostics` is populated when cascade is active

### 9. Isolation

- running cascade does not modify any individual signal value
- signals that do not fire at Stage 1/2 still produce the same values when they fire at Stage 3

## Rollout Plan

### Step 1 -- shadow mode

- enable cascade alongside single-stage (both run, cascade results are diagnostics-only)
- compare top-10 agreement and NDCG@10 between cascade and single-stage
- measure actual compute savings

### Step 2 -- operator review

- verify top-10 agreement is consistently >= 8/10
- verify NDCG@10 degradation is < 5%
- verify compute savings are >= 2x
- review which signals are correctly classified as cheap/medium/expensive

### Step 3 -- switchover

- only after shadow mode confirms quality and savings
- switch primary pipeline to cascade
- keep single-stage as a fallback option

## Risk List

- Stage 1 may incorrectly filter out a candidate that would have been top-10 in single-stage -- mitigated by keeping `stage1_keep = 200` (generous buffer) and monitoring top-10 agreement;
- tiny neural networks may underfit complex feature interactions -- mitigated by the fact that each stage only needs to make coarse quality distinctions, not fine-grained rankings;
- feature classification (cheap/medium/expensive) may not match actual compute costs -- mitigated by operator-configurable feature assignment;
- training on pruned sets may introduce selection bias -- mitigated by periodically retraining with fresh pruned sets from recent pipeline runs;
- the cascade adds architectural complexity -- mitigated by defaulting to `enabled = false` and providing a single-stage fallback.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"cascade.enabled": "false",
"cascade.stage1_keep": "200",
"cascade.stage2_keep": "50",
"cascade.stage3_return": "10",
"cascade.retrain_interval_days": "7",
"cascade.min_training_items": "200",
```

**Why these values:**

- `enabled = false` -- cascade is an architectural change that requires validation via shadow mode before activation. It defaults to off.
- `stage1_keep = 200` -- generous first-pass retention to minimise risk of filtering out good candidates.
- `stage2_keep = 50` -- enough candidates for Stage 3 to have meaningful discrimination.
- `stage3_return = 10` -- final top-10 aligns with the current UI display limit.
- `retrain_interval_days = 7` -- weekly retraining keeps stage models current.
- `min_training_items = 200` -- ensures each stage has enough examples for training.

### Migration note

FR-068 must ship a new data migration that upserts these six keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
