# FR-067 - Markov Chain Rank Aggregation

## Confirmation

- **Backlog confirmed**: `FR-067 - Markov Chain Rank Aggregation` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No supervised rank aggregation exists in the current system. The closest planned mechanism is RRF (FR-046), which uses a fixed unsupervised formula to merge ranked lists. FR-067 learns optimal per-source mixing weights from editorial judgments via Markov chain stationary distributions solved by semidefinite programming (SDP) -- a fundamentally different mathematical framework.
- **Repo confirmed**: The existing C++ extensions pattern in `backend/extensions/` supports the SDP solver and matrix operations needed for `rankagg.cpp`. The SCS (Splitting Conic Solver) library provides the SDP solving capability.

## Current Repo Map

### Rank fusion already planned

- `FR-046 Query Fan-Out Stage-1 Retrieval` includes RRF (Reciprocal Rank Fusion):
  - Fixed formula: `RRF_score(d) = SUM_k 1 / (60 + rank_k(d))` where `k` indexes ranking sources.
  - No learning: the constant 60 and equal source weights are fixed. RRF does not adapt to which sources are more reliable.

### Ranking sources already available

Each of these sources produces its own ordering of link candidates:

- `score_semantic` -- semantic embedding similarity ranking
- `score_keyword` -- Jaccard keyword overlap ranking
- `score_authority` -- authority/PageRank ranking
- `score_freshness` -- link freshness ranking
- `score_phrase_match` -- phrase matching ranking
- `score_field_bm25` -- field-aware BM25 ranking
- `score_click_distance` -- click distance ranking
- `score_feedback_ucb` -- feedback explore/exploit ranking
- Plus any new signals from FR-038 onward

### Training data already available

- `backend/apps/suggestions/models.py`
  - Editor-labelled suggestions: approved/rejected per (source_page, batch) group.
  - These provide the ground-truth pairwise orderings: if A is approved and B is rejected in the same batch, then A should rank above B.

## Source Summary

### Patent: US7840522B2 -- Supervised Rank Aggregation Based on Rankings (Microsoft, Tie-Yan Liu, 2010)

**Plain-English description of the patent:**

The patent describes constructing a Markov chain transition matrix from each ranking source (where states are candidates and transitions encode pairwise ordering), then learning per-source mixing weights so the combined chain's stationary distribution best matches editorial ground-truth orderings. The optimal weights are found via semidefinite programming (SDP), which provides a globally optimal solution (no local optima).

**Repo-safe reading:**

The patent targets web search with many ranking features. This repo has 8-20+ ranking signals, each producing its own candidate ordering per source page. The Markov chain framework works directly on these orderings without requiring raw scores, making it ideal for combining heterogeneous signals whose scores are on different scales.

**What is directly supported by the patent:**

- constructing Markov chain transition matrices from ranked lists;
- learning mixing weights via SDP;
- computing the combined stationary distribution as the final ranking;
- proving global optimality of the SDP solution.

**What is adapted for this repo:**

- "ranking sources" map to the individual scoring signals;
- "queries" map to (source_page, batch) groups;
- the SCS library provides the SDP solver (free, C-based);
- the stationary distribution is computed via power iteration (simple, efficient);
- the learned source weights can be compared against L-BFGS/RankBoost/SmoothRank weights for cross-validation.

## Plain-English Summary

Simple version first.

Imagine you have 8 judges scoring a cooking competition. Each judge ranks the dishes differently based on their expertise: one judge focuses on presentation, another on flavour, another on technique. You need to combine their rankings into one final ranking.

RRF (FR-046) gives every judge equal say and uses a fixed formula. It works but ignores the fact that some judges might be better than others, or that certain judges might be better for certain types of dishes.

FR-067 learns which judges to trust more. It looks at past competitions where the winner is known (the editorial ground truth) and figures out: "Judge A's rankings consistently predicted the winner, but Judge C's rankings were almost random." Then it gives Judge A more influence in the combined ranking.

The clever part is how it combines the rankings. Each judge's ranking becomes a "Markov chain" -- imagine a random walker on the candidates who tends to move toward higher-ranked items. The combined Markov chain blends the judges' chains with learned weights. The final ranking is the "stationary distribution" -- where the random walker ends up spending most of their time. Items that many weighted judges rank highly attract the most attention from the walker.

The weights are found via SDP (semidefinite programming), which guarantees the globally optimal solution. No local optima, no lucky initialisation -- the math guarantees the best possible combination.

## Problem Statement

Current and planned rank fusion methods have limitations:

1. **RRF (FR-046)**: fixed formula, equal source weights, no learning. Cannot adapt to which signals are more predictive.
2. **L-BFGS (FR-018)**: tunes weights on raw scores, which requires scores to be on comparable scales. Heterogeneous signals (e.g., a 0-1 similarity score vs. a 0-100 authority score) need manual normalisation.
3. **Direct score weighting**: all weight tuning methods assume scores are meaningful. But ordinal rankings may be more robust than raw scores for some signals.

FR-067 works directly with ordinal rankings (no raw scores needed), learns from editorial judgments, and provides globally optimal mixing weights via SDP.

## Goals

FR-067 should:

- construct a Markov chain transition matrix per ranking source from ordinal rankings;
- learn per-source mixing weights via SDP that minimise distance to ground-truth rankings;
- compute the combined Markov chain's stationary distribution via power iteration;
- produce a final rank score per candidate based on stationary probabilities;
- keep the score additive on top of existing ranking, off by default (weight = 0.0);
- implement the transition matrix construction and power iteration in C++ (`rankagg.cpp`);
- use the SCS library for SDP solving;
- fit within ~15 MB RAM (small transition matrices + weight vector + SDP workspace).

## Non-Goals

FR-067 does not:

- replace RRF (FR-046) -- it provides a supervised alternative;
- modify any individual signal computation or score;
- require a GPU or heavy compute resources;
- handle time-varying source reliability (static weights per model retraining);
- implement online learning (batch training only);
- implement production code in the spec pass.

## Math-Fidelity Note

### Transition matrix construction

For each ranking source `k` (semantic, BM25, authority, etc.) and a batch of `n` candidates:

```text
T_k(i, j) = (n - rank_k(i)) / SUM_m (n - rank_k(m))    if i is ranked above j by source k
           = 0                                             otherwise
```

This creates a stochastic matrix where the random walker transitions toward higher-ranked items. The transition probability from state `j` to state `i` is proportional to `i`'s ranking strength.

### Ground-truth matrix

From editorial labels (approved/rejected):

```text
T*(i, j) = 1    if editorial label says i should rank above j (i approved, j rejected)
         = 0    otherwise

Normalise T* to be a valid transition matrix (row sums = 1)
```

### SDP optimisation

Find mixing weights `lambda = (lambda_1, ..., lambda_K)` for `K` ranking sources:

```text
Minimise    ||T* - SUM_k lambda_k * T_k||_F^2     [Frobenius norm]

Subject to: lambda_k >= 0 for all k
            SUM_k lambda_k = 1
```

Solved via SCS (Splitting Conic Solver), which handles the semidefinite constraint and provides globally optimal `lambda`.

### Combined transition matrix

```text
T_mix = SUM_k lambda_k * T_k
```

### Stationary distribution (power iteration)

```text
Initialise: pi_0 = uniform distribution (1/n, ..., 1/n)

Iterate: pi_{t+1} = pi_t * T_mix

Until: ||pi_{t+1} - pi_t|| < 1e-6 or max_iter=1000 reached
```

The stationary distribution `pi` gives the long-run probability that the random walker visits each candidate. Higher `pi(i)` means candidate `i` is consistently ranked well by the weighted combination of sources.

### Final score

```text
rankagg_score(i) = pi(i) / max(pi)    [normalise to [0, 1]]
```

### C++ extension signatures

```text
rankagg.cpp:
  void build_transition(
    const int* ranks,    // n ranks from one source
    int n,               // number of candidates
    float* T_out         // n x n transition matrix (output)
  )

  void power_iter(
    const float* T,      // n x n combined transition matrix
    int n,               // number of candidates
    float* pi,           // n stationary probabilities (output)
    int max_iter         // maximum iterations
  )
```

### Computational complexity

```text
Transition construction: O(K * n^2) per batch
SDP solving: polynomial in K and n (typically seconds for K=20, n=50)
Power iteration: O(n^2 * max_iter) per batch

For typical sizes (K=8-20 sources, n=10-50 candidates):
  Total: < 100ms per batch
```

### RAM budget

```text
K transition matrices: K * n * n * 4 bytes = 8 * 50 * 50 * 4 = 80 KB per batch
SDP workspace: ~2 MB
Weight vector: K * 4 bytes = 80 bytes
Total: ~3 MB per query batch, ~15 MB total with overhead
```

## Scope Boundary Versus Existing Signals

FR-067 must stay separate from:

- `RRF (FR-046)`
  - RRF uses a fixed unsupervised formula with no learning;
  - FR-067 learns per-source weights from editorial judgments via SDP;
  - different mathematical framework (rank reciprocal vs. Markov chain stationary distribution).

- `L-BFGS weight tuning (FR-018)`
  - L-BFGS tunes weights on raw scores via gradient descent;
  - FR-067 learns mixing weights on ordinal rankings via SDP;
  - different inputs (scores vs. ranks) and different solver (gradient descent vs. SDP).

- `SmoothRank (FR-066)`
  - SmoothRank optimises smooth NDCG via gradient ascent on the weight vector;
  - FR-067 optimises Frobenius distance between combined and ground-truth Markov chains via SDP;
  - different objective and different solver.

- `Spectral Relational Clustering (FR-064)`
  - spectral RC clusters objects via eigen decomposition of relation matrices;
  - FR-067 aggregates rankings via Markov chain stationary distributions;
  - both use spectral methods but for completely different purposes.

Hard rule: FR-067 must not modify any individual signal computation or any ranking score. It reads ordinal rankings from each source and produces one additive score per candidate.

## Inputs Required

FR-067 uses only data already available:

- Per-source ordinal rankings: sort each signal's scores within a batch to get ranks
- `Suggestion.status` -- editorial labels for ground-truth pairwise ordering
- `Suggestion.pipeline_run_id` + `Suggestion.host_content_item_id` -- batch grouping

Explicitly disallowed inputs:

- raw signal scores (FR-067 operates on ordinal ranks only)
- analytics data directly
- any data not derived from existing Suggestion records

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `rankagg.enabled`
- `rankagg.ranking_weight`
- `rankagg.power_iter_max`
- `rankagg.min_training_batches`
- `rankagg.retrain_interval_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `power_iter_max = 1000`
- `min_training_batches = 50`
- `retrain_interval_days = 7`

Bounds:

- `0.0 <= ranking_weight <= 0.15`
- `100 <= power_iter_max <= 10000`
- `20 <= min_training_batches <= 500`
- `1 <= retrain_interval_days <= 30`

### Feature-flag behavior

- `enabled = false`
  - skip rank aggregation entirely
  - store `score_rankagg = 0.5`
  - store `rankagg_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - compute aggregation and store diagnostics
  - do not change ranking order
- `enabled = true` and insufficient training data
  - store `score_rankagg = 0.5`
  - store `rankagg_state = neutral_insufficient_data`

## Diagnostics And Explainability Plan

Add one new diagnostics object per suggestion:

- `Suggestion.rankagg_diagnostics`

Required per-suggestion fields:

- `score_rankagg` -- stationary probability normalised to [0, 1]
- `rankagg_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_insufficient_data`
  - `neutral_model_not_found`
  - `neutral_processing_error`
- `stationary_probability` -- raw pi(i) before normalisation
- `per_source_ranks` -- this candidate's rank from each source
- `batch_size` -- number of candidates in this batch
- `power_iterations_used` -- how many iterations until convergence

System-level diagnostics:

- `source_weights` -- the learned lambda vector (how much each source contributes)
- `source_weight_ranking` -- sources sorted by learned weight (most to least trusted)
- `sdp_objective_value` -- how well the combined chain matches ground truth
- `training_batches_used` -- number of batches used for SDP training
- `model_version` -- timestamp

Plain-English review helper text should say:

- `Rank aggregation combines multiple ranking signals using learned source weights.`
- `Higher scores mean this suggestion is consistently ranked highly by the most trusted signals.`
- `Source weights show which signals the system trusts most based on past editor decisions.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_rankagg: FloatField(default=0.5)`
- `rankagg_diagnostics: JSONField(default=dict, blank=True)`

### Model file storage

- Learned source weights serialised to `backend/ml_models/rankagg_weights.json`
- File size: < 1 KB (just a weight vector of K floats)

### C++ extension

- `backend/extensions/rankagg.cpp` -- new C++ pybind11 extension
- Follows existing build pattern in `backend/extensions/CMakeLists.txt`
- SCS library linked for SDP solving

### PipelineRun snapshot

Add FR-067 settings, source weights, and model version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/rankagg/`
- `PUT /api/settings/rankagg/`
- `POST /api/settings/rankagg/retrain/` -- triggers manual retraining
- `GET /api/settings/rankagg/diagnostics/` -- returns source weights and quality metrics

### Review / admin / frontend

Add one new review row:

- `Rank Aggregation Score`

Add one small diagnostics block:

- stationary probability and per-source ranks
- convergence iterations

Add one settings card:

- enabled toggle
- ranking weight slider
- power iteration maximum
- minimum training batches
- retrain interval
- manual retrain button
- source weight bar chart (learned weights per signal)

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/extensions/rankagg.cpp` -- new C++ extension
- `backend/extensions/CMakeLists.txt` -- add rankagg build target
- `backend/apps/pipeline/services/rank_aggregation.py` -- new service file
- `backend/apps/pipeline/services/ranker.py` -- add FR-067 additive hook
- `backend/apps/pipeline/tasks.py` -- add periodic retraining task
- `backend/apps/suggestions/models.py` -- add two new fields
- `backend/apps/suggestions/serializers.py` -- expose new fields
- `backend/apps/suggestions/views.py` -- snapshot FR-067 settings
- `backend/apps/suggestions/admin.py` -- expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` -- add settings and diagnostics endpoints
- `backend/apps/api/urls.py` -- wire new endpoints
- `backend/apps/pipeline/tests.py` -- FR-067 unit tests
- `backend/requirements.txt` -- add SCS solver dependency (if not using C++ directly)
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched:

- All individual signal computation files
- `backend/apps/content/models.py`
- `backend/apps/graph/models.py`

## Test Plan

### 1. Transition matrix construction

- candidate ranked 1st by a source gets the highest transition probabilities
- transition matrix rows sum to 1 (valid stochastic matrix)
- n candidates produce an n x n matrix

### 2. SDP optimisation

- with one source perfectly matching ground truth: that source gets weight ~1.0
- with all sources equally good: weights are approximately equal
- all weights are non-negative and sum to 1

### 3. Power iteration convergence

- stationary distribution converges within max_iter iterations
- stationary probabilities sum to 1
- higher-ranked candidates (by combined Markov chain) get higher stationary probability

### 4. Score normalisation

- normalised score is in [0, 1]
- the candidate with the highest stationary probability gets score 1.0

### 5. Neutral fallback cases

- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`
- insufficient training data -> `score = 0.5`, state `neutral_insufficient_data`
- model file missing -> `score = 0.5`, state `neutral_model_not_found`

### 6. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 7. Isolation

- rank aggregation does not modify any signal score or weight
- the learned source weights are stored separately from `recommended_weights.py`

### 8. C++ extension

- `build_transition` produces identical results to a pure Python reference
- `power_iter` converges to the same stationary distribution as NumPy matrix power iteration

## Rollout Plan

### Step 1 -- training and diagnostics only

- learn source weights with `ranking_weight = 0.0`
- inspect which sources the SDP trusts most
- compare learned source weights against manually set weights

### Step 2 -- operator review

- verify that highly weighted sources are indeed the most predictive
- check whether rank aggregation scores correlate with approval rates
- compare rank aggregation against the existing weighted sum

### Step 3 -- optional ranking enablement

- only after operator verification passes
- recommended first live weight: `0.03` to `0.05`

## Risk List

- SDP solver may be slow for large K (many sources) -- mitigated by typical K=8-20 which solves in seconds;
- sparse editorial labels may not provide enough pairwise constraints for reliable SDP -- mitigated by `min_training_batches` threshold;
- the Markov chain framework assumes transitivity (if A > B and B > C then A > C) which may not always hold -- mitigated by the SDP's robustness to noise;
- SCS library adds a build dependency -- mitigated by following the existing C++ extension pattern and providing a Python fallback using cvxpy.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"rankagg.enabled": "true",
"rankagg.ranking_weight": "0.04",
"rankagg.power_iter_max": "1000",
"rankagg.min_training_batches": "50",
"rankagg.retrain_interval_days": "7",
```

**Why these values:**

- `enabled = true` -- learn source weights from day one for diagnostic insight.
- `ranking_weight = 0.04` -- conservative; rank aggregation provides a novel ranking perspective but needs validation.
- `power_iter_max = 1000` -- sufficient for convergence on any reasonable batch size.
- `min_training_batches = 50` -- ensures enough labelled data for reliable SDP training.
- `retrain_interval_days = 7` -- weekly retraining as new editorial labels arrive.

### Migration note

FR-067 must ship a new data migration that upserts these five keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
