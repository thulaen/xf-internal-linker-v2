# FR-066 - SmoothRank NDCG Optimisation

## Confirmation

- **Backlog confirmed**: `FR-066 - SmoothRank NDCG Optimisation` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No direct metric optimisation exists in the current system. L-BFGS weight tuning (FR-018) optimises a proxy loss (cross-entropy). ListNet (FR-060) uses Plackett-Luce permutation probabilities as a surrogate. FR-066 directly targets the actual ranking quality metric (NDCG) by making it differentiable through sigmoid smoothing -- a fundamentally different optimisation target.
- **Repo confirmed**: The existing C++ extensions pattern in `backend/extensions/` provides the build infrastructure for `smoothrank.cpp`. The numerical computations (sigmoid, dot products, gradient descent) are well-suited to a C++ pybind11 extension.

## Current Repo Map

### Weight tuning already available

- `backend/apps/pipeline/services/ranker.py`
  - Composite score is `score_final = SUM_i w_i * score_i`.
  - Weights `w` are tuned by L-BFGS (FR-018) on a proxy loss.

- `backend/extensions/`
  - Existing C++ pybind11 extensions (`scoring.cpp`, `simsearch.cpp`, `fieldrel.cpp`, etc.).
  - Build infrastructure (CMakeLists.txt, pybind11 setup) already in place.
  - `smoothrank.cpp` follows the same pattern.

### Training data already available

- `backend/apps/suggestions/models.py`
  - `Suggestion` rows with editor-assigned relevance (approved/rejected, or graded if FR-063 grades exist).
  - Feature vectors: all `score_*` fields per suggestion.
  - Grouped by `pipeline_run_id` for query-level NDCG computation.

## Source Summary

### Patent: US7895198B2 -- Gradient Based Optimisation of a Ranking Measure (Yahoo, 2011)

**Plain-English description of the patent:**

The patent describes creating a smooth, differentiable approximation of NDCG (which is normally non-differentiable because it depends on sorting). The key insight: replace the hard sorting operation with a soft approximation using sigmoid functions. Each item's rank position is approximated as a continuous function of the score differences. Standard gradient descent can then directly optimise this smooth NDCG with respect to the scoring function's parameters.

**Repo-safe reading:**

The patent uses arbitrary neural networks as the scoring function. This repo uses a linear scoring function (weighted sum of signals), so the gradients simplify considerably. The C++ extension handles the smooth NDCG computation and gradient calculation; the weight update loop runs in Python.

**What is directly supported by the patent:**

- sigmoid-based smooth rank approximation;
- differentiable DCG and NDCG computation;
- gradient ascent directly on the smooth NDCG objective.

**What is adapted for this repo:**

- linear scoring function instead of a neural network;
- the weight vector is the same one used by the existing composite scorer;
- temperature annealing (starting warm, cooling toward hard ranking) for convergence;
- C++ extension for the numerically intensive inner loop.

## Plain-English Summary

Simple version first.

NDCG (Normalized Discounted Cumulative Gain) is the standard measure of how good a ranked list is. It checks whether the best items appear near the top. The problem: NDCG involves sorting, and sorting is not smooth -- a tiny score change can cause two items to swap positions, causing a sudden jump in NDCG. You cannot do calculus on jumps.

L-BFGS (FR-018) works around this by optimising a "proxy" loss (like cross-entropy) that is smooth but only approximately related to NDCG. It is like tuning a car engine by optimising fuel economy and hoping that also makes the car faster. Usually it helps, but it is indirect.

FR-066 makes NDCG itself smooth. Instead of hard sorting (item A is definitely at position 3), it uses "soft" sorting: "item A is approximately at position 3.2, with some probability of being at 2.8 or 3.6." This is done with sigmoid functions that make the transition between "A is above B" and "A is below B" gradual rather than sudden.

With smooth NDCG, standard gradient descent can directly optimise the weights to maximise ranking quality -- not a proxy, not a surrogate, but the actual metric the operator cares about.

The temperature parameter controls how "soft" the sorting is. It starts warm (very soft, easy to optimise) and gradually cools (approaches the real hard NDCG), like simulated annealing.

## Problem Statement

Current weight optimisation methods target proxy objectives:

1. **L-BFGS (FR-018)**: optimises cross-entropy loss. This loss is smooth but only loosely correlated with NDCG. Weights that minimise cross-entropy may not maximise NDCG.
2. **ListNet (FR-060)**: uses Plackett-Luce permutation probabilities as a surrogate. Better than pointwise cross-entropy, but still an approximation of the true ranking metric.
3. **RankBoost (FR-061)**: optimises pairwise accuracy. This is related to NDCG but does not account for position discounting (top-of-list errors matter more than bottom-of-list errors).

FR-066 directly maximises a smooth approximation of NDCG itself. As the temperature anneals toward zero, the smooth approximation converges to the true NDCG, meaning the weights are tuned to directly maximise ranking quality.

## Goals

FR-066 should:

- compute a differentiable smooth NDCG approximation using sigmoid-based soft ranks;
- compute gradients of smooth NDCG with respect to the weight vector via backpropagation through the sigmoid;
- run gradient ascent to maximise smooth NDCG on labelled suggestion batches;
- anneal the temperature parameter from warm (1.0) to cool (0.05) across training epochs;
- produce an optimised weight vector for operator review before applying;
- implement the numerically intensive inner loop in C++ (`smoothrank.cpp`);
- keep the optimisation off by default until the operator reviews the suggested weights;
- fit within ~10 MB RAM (weight vector + gradient vector + sigmoid lookup table).

## Non-Goals

FR-066 does not:

- replace L-BFGS, ListNet, or RankBoost -- it provides a complementary optimisation target;
- modify the ranking pipeline at inference time -- it only optimises the weight vector offline;
- use a neural network scoring function (linear weights only);
- create new features or signals;
- require GPU;
- implement production code in the spec pass.

## Math-Fidelity Note

### Smooth rank approximation

For item `i` in a batch of `n` candidates with scores `s_1, ..., s_n`:

```text
pi_sigma(i) = 1 + SUM_{j != i} sigma((s_j - s_i) / sigma_temp)
```

where `sigma(x) = 1 / (1 + exp(-x))` is the sigmoid function and `sigma_temp` is the temperature parameter.

This approximates item `i`'s rank position. When `sigma_temp` is large, the sigmoid is gradual and the rank is "soft." When `sigma_temp` approaches zero, the sigmoid approaches a step function and the soft rank converges to the true hard rank.

### Smooth DCG

```text
G(rel_i) = 2^{rel_i} - 1                    [grade gain; rel_i in {0, 1, 2, 3}]
D(pi_i)  = 1 / log_2(pi_sigma(i) + 1)       [soft discount]

DCG_smooth = SUM_i G(rel_i) * D(pi_sigma(i))
```

### Smooth NDCG

```text
IDCG = DCG computed with items sorted by true relevance (ideal ranking)
NDCG_smooth = DCG_smooth / IDCG
```

IDCG is constant with respect to the weight vector, so maximising `DCG_smooth` is equivalent to maximising `NDCG_smooth`.

### Gradient computation

For a linear scoring function `s_i = w . x_i` (dot product of weight vector and feature vector):

```text
dDCG_smooth/ds_i = SUM_{j != i} [ G(rel_i) * dD(pi_i)/ds_i + G(rel_j) * dD(pi_j)/ds_i ]

dD(pi_i)/ds_i uses the chain rule through the sigmoid:
  d_sigma(x)/dx = sigma(x) * (1 - sigma(x))

dw = SUM_i (dDCG_smooth/ds_i) * x_i        [gradient w.r.t. weight vector]
```

### Training loop

```text
Initialise: w = current weight vector from recommended_weights.py
            sigma_temp = 1.0
            learning_rate = 0.01

For epoch = 1..100:
  For each batch of labelled suggestions:
    s = w . X                                [compute scores]
    Compute DCG_smooth and gradient dw       [via smoothrank.cpp]
    w <- w + learning_rate * dw              [gradient ascent, maximising NDCG]

  sigma_temp <- max(0.05, sigma_temp * 0.95)  [anneal temperature]

Output: optimised weight vector w
```

### C++ extension signature

```text
smoothrank.cpp:
  void smoothrank_step(
    const float* scores,     // n scores
    const float* rels,       // n relevance grades
    const float* features,   // n x d feature matrix
    int n,                   // batch size
    int d,                   // feature dimension
    float sigma,             // temperature
    float lr,                // learning rate
    float* weights           // d weights (updated in-place)
  )
```

### Computational complexity per batch

```text
Soft ranks: O(n^2)           [pairwise sigmoid computation]
Gradients:  O(n^2 * d)       [chain rule through n x n sigmoid matrix]
```

For typical batch sizes (n=10-50), this is negligible. The C++ extension makes it fast even for n=200.

### RAM budget

```text
Weight vector: d * 4 bytes ~ 200 bytes
Gradient vector: d * 4 bytes ~ 200 bytes
Sigmoid table (n x n per batch): n^2 * 4 bytes ~ 40 KB for n=100
Total: ~10 MB with all overhead
```

## Scope Boundary Versus Existing Signals

FR-066 must stay separate from:

- `L-BFGS weight tuning (FR-018)`
  - L-BFGS optimises a proxy loss (cross-entropy);
  - FR-066 optimises smooth NDCG (direct metric);
  - different objective function, same output (weight vector).

- `ListNet listwise ranking (FR-060)`
  - ListNet uses Plackett-Luce permutation probabilities;
  - FR-066 uses sigmoid-based smooth ranks;
  - different surrogate mechanism.

- `RankBoost weight optimisation (FR-061)`
  - RankBoost uses boosting on pairwise preferences;
  - FR-066 uses gradient ascent on smooth NDCG;
  - different optimisation paradigm (boosting vs. continuous gradient).

- `Multi-Hyperplane Ranker (FR-063)`
  - MHR trains grade-pair SVMs and aggregates via BordaCount;
  - FR-066 tunes the linear weight vector directly;
  - different model types and different aggregation.

Hard rule: FR-066 must not modify any signal computation or any model other than the weight vector. It reads feature vectors and labels, optimises weights, and outputs a suggested weight vector.

## Inputs Required

FR-066 uses only data already available:

- `Suggestion` feature vectors: all `score_*` fields
- `Suggestion.status` or extended grade labels for relevance grades
- `Suggestion.pipeline_run_id` for batch grouping
- Current weight vector from `recommended_weights.py`

Explicitly disallowed inputs:

- raw text, embeddings, or analytics data
- any data not already stored on the Suggestion model

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `smoothrank.enabled`
- `smoothrank.learning_rate`
- `smoothrank.initial_temperature`
- `smoothrank.temperature_decay`
- `smoothrank.min_temperature`
- `smoothrank.epochs`
- `smoothrank.min_training_batches`
- `smoothrank.auto_apply`

Defaults:

- `enabled = true`
- `learning_rate = 0.01`
- `initial_temperature = 1.0`
- `temperature_decay = 0.95`
- `min_temperature = 0.05`
- `epochs = 100`
- `min_training_batches = 50`
- `auto_apply = false`

Bounds:

- `0.001 <= learning_rate <= 0.1`
- `0.1 <= initial_temperature <= 5.0`
- `0.8 <= temperature_decay <= 0.99`
- `0.01 <= min_temperature <= 0.5`
- `10 <= epochs <= 500`
- `20 <= min_training_batches <= 500`

### Feature-flag behavior

- `enabled = false`
  - skip SmoothRank computation entirely
  - store `smoothrank_state = disabled`
- `enabled = true` and `auto_apply = false`
  - compute suggested weights, store in diagnostics for operator review
  - do not apply to live ranking
- `enabled = true` and insufficient training data
  - store `smoothrank_state = insufficient_data`

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `SmoothRankDiagnostics` (stored system-wide, not per-suggestion)

Required fields:

- `smoothrank_state` -- `computed`, `disabled`, `insufficient_data`
- `suggested_weights` -- the weight vector produced by SmoothRank
- `current_weights` -- the weight vector before optimisation
- `weight_deltas` -- per-signal change
- `initial_ndcg` -- smooth NDCG before optimisation
- `final_ndcg` -- smooth NDCG after optimisation
- `ndcg_improvement` -- percentage improvement
- `epochs_completed` -- number of training epochs
- `final_temperature` -- temperature at the end of annealing
- `convergence_history` -- NDCG per epoch (for plotting)
- `training_batches_used` -- number of labelled batches
- `model_version` -- timestamp

Plain-English review helper text should say:

- `SmoothRank directly optimises ranking quality (NDCG) by making it mathematically smooth.`
- `The suggested weights are tuned to put the best suggestions at the top of the list.`
- `NDCG improvement shows how much better the suggested weights rank compared to current weights.`

## Storage / Model / API Impact

### System-level model

- No per-suggestion storage needed -- FR-066 operates on weights, not scores.
- Store `SmoothRankDiagnostics` as a JSON record in `AppSetting`.

### C++ extension

- `backend/extensions/smoothrank.cpp` -- new C++ pybind11 extension
- Follows existing build pattern in `backend/extensions/CMakeLists.txt`
- Compiled once, called from Python service

### Weight staging

- Suggested weights stored in `AppSetting` key `smoothrank.suggested_weights`
- Operator reviews and either applies or discards

### PipelineRun snapshot

Add FR-066 state to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/smoothrank/`
- `PUT /api/settings/smoothrank/`
- `POST /api/settings/smoothrank/run/` -- triggers manual optimisation
- `POST /api/settings/smoothrank/apply/` -- applies suggested weights
- `GET /api/settings/smoothrank/diagnostics/` -- returns diagnostics with convergence history

### Review / admin / frontend

Add one settings card:

- enabled toggle
- learning rate input
- temperature parameters (initial, decay, minimum)
- epochs slider
- minimum batches input
- auto-apply toggle (with warning)
- "Run Now" button
- convergence chart (NDCG per epoch)
- weight comparison table (current vs. suggested vs. delta)
- NDCG improvement display

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/extensions/smoothrank.cpp` -- new C++ extension
- `backend/extensions/CMakeLists.txt` -- add smoothrank build target
- `backend/apps/pipeline/services/smoothrank_optimizer.py` -- new service file
- `backend/apps/pipeline/tasks.py` -- add periodic optimisation task
- `backend/apps/suggestions/recommended_weights.py` -- update hook for applying weights
- `backend/apps/core/views.py` -- add settings and diagnostics endpoints
- `backend/apps/api/urls.py` -- wire new endpoints
- `backend/apps/pipeline/tests.py` -- FR-066 unit tests
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched:

- `backend/apps/pipeline/services/ranker.py` -- no inference-time changes
- All individual signal computation files
- `backend/apps/content/models.py`
- `backend/apps/suggestions/models.py` -- no per-suggestion fields needed

## Test Plan

### 1. Smooth rank approximation

- with high temperature (sigma_temp=10), soft ranks are nearly uniform (all items have similar soft rank)
- with low temperature (sigma_temp=0.01), soft ranks approximate hard ranks
- soft rank of the highest-scoring item is always closest to 1

### 2. Smooth NDCG computation

- perfect ranking (items sorted by relevance) produces maximum smooth NDCG
- reversed ranking produces minimum smooth NDCG
- smooth NDCG approaches true NDCG as temperature -> 0

### 3. Gradient correctness

- numerical gradient (finite differences) matches analytical gradient within tolerance (1e-4)
- gradient direction is ascending (w + lr * dw produces higher NDCG)

### 4. Temperature annealing

- temperature decreases by factor 0.95 each epoch
- temperature never drops below min_temperature (0.05)

### 5. Convergence

- NDCG increases (or stays flat) across epochs
- final NDCG >= initial NDCG on training data

### 6. Insufficient data

- fewer than `min_training_batches` -> state `insufficient_data`, no weights suggested

### 7. Weight application

- `auto_apply = false` -> weights stored but not applied
- `auto_apply = true` -> weights applied after operator review

### 8. C++ extension

- `smoothrank_step` produces identical results to a pure Python reference implementation
- C++ version is at least 10x faster than Python for n=100, d=50

## Rollout Plan

### Step 1 -- diagnostics only

- run SmoothRank with `auto_apply = false`
- inspect convergence history (NDCG should increase across epochs)
- compare suggested weights against current weights and L-BFGS suggestions

### Step 2 -- operator comparison

- compare SmoothRank, L-BFGS, and RankBoost weight suggestions
- investigate signals where they disagree
- test SmoothRank weights on a shadow pipeline run

### Step 3 -- optional application

- only after operator verification passes
- apply suggested weights and monitor NDCG on live data

## Risk List

- smooth NDCG may have local optima that gradient ascent cannot escape -- mitigated by temperature annealing which creates a smoother landscape initially;
- the sigmoid approximation introduces a gap between smooth NDCG and true NDCG -- mitigated by annealing to a very low temperature (0.05) which makes the gap negligible;
- training on small datasets may produce overfitted weights -- mitigated by `min_training_batches` threshold and the simplicity of the linear model (low capacity);
- the C++ extension adds build complexity -- mitigated by following the existing extension pattern exactly.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"smoothrank.enabled": "true",
"smoothrank.learning_rate": "0.01",
"smoothrank.initial_temperature": "1.0",
"smoothrank.temperature_decay": "0.95",
"smoothrank.min_temperature": "0.05",
"smoothrank.epochs": "100",
"smoothrank.min_training_batches": "50",
"smoothrank.auto_apply": "false",
```

**Why these values:**

- `enabled = true` -- compute suggested weights from day one for operator review.
- `learning_rate = 0.01` -- conservative; prevents large weight jumps from noisy gradients.
- `initial_temperature = 1.0` -- starts with a smooth landscape for reliable early convergence.
- `temperature_decay = 0.95` -- gradual cooling over 100 epochs reaches final temperature of ~0.006.
- `min_temperature = 0.05` -- prevents numerical instability from very sharp sigmoids.
- `epochs = 100` -- sufficient for convergence on typical datasets.
- `min_training_batches = 50` -- ensures enough data for reliable NDCG estimates.
- `auto_apply = false` -- operator must review before any weight change goes live.

### Migration note

FR-066 must ship a new data migration that upserts these eight keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
