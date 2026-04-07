# FR-061 - RankBoost Weight Optimisation

## Confirmation

- **Backlog confirmed**: `FR-061 - RankBoost Weight Optimisation` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No boosting-based weight optimiser exists in the current system. The closest mechanism is L-BFGS weight tuning (FR-018), which uses gradient descent on a differentiable loss. FR-061 uses AdaBoost-style iterative boosting on pairwise preferences derived from real user behaviour data -- a fundamentally different optimisation paradigm.
- **Repo confirmed**: GSC click data, Matomo session CTR, and GA4 engagement metrics are already ingested and stored. These three sources provide the pairwise preference pairs that drive the boosting iterations.

## Current Repo Map

### Weight tuning already available

- `backend/apps/pipeline/services/ranker.py`
  - `_calculate_composite_scores_full_batch_py(...)` -- computes weighted sum using the current weight vector.
  - The weights are either manually set or tuned by L-BFGS (FR-018).

- `backend/apps/suggestions/recommended_weights.py`
  - `RECOMMENDED_PRESET_WEIGHTS` -- the weight dictionary that FR-061 would update with learned adjustments.

### Feedback data already available

- `backend/apps/analytics/` -- GA4 session engagement metrics per destination page (session duration, bounce rate).
- `backend/apps/search_console/` -- GSC click/impression data per destination page.
- `backend/apps/matomo/` -- Matomo per-suggestion CTR data.
- These three data sources can generate pairwise preference pairs: "link A performed better than link B in the same context."

## Source Summary

### Patent: US8301638B2 -- Automated Feature Selection Based on RankBoost (Microsoft, 2012)

**Plain-English description of the patent:**

The patent describes using the RankBoost algorithm (an AdaBoost variant for ranking) to automatically identify which features are most discriminative for ranking quality. Each boosting round selects the single best feature-threshold pair that most improves pairwise ranking accuracy, then upweights the misranked pairs for the next round. The learned coefficients per weak ranker indicate feature importance.

**Repo-safe reading:**

The patent describes full feature selection (including dropping features). This repo uses RankBoost in **weights-only mode** -- it adjusts signal weights up or down but never drops a signal entirely. All signals remain active with a minimum floor weight. This is a deliberate constraint to maintain diagnostics coverage and operator transparency.

**What is directly supported by the patent:**

- iterative boosting on pairwise preferences;
- feature-threshold weak rankers as the base hypothesis class;
- learned alpha coefficients indicating feature importance.

**What is adapted for this repo:**

- "feature selection" is restricted to "weight adjustment" -- no signal is ever zeroed out;
- pairwise preferences come from GSC/Matomo/GA4 behaviour data, not editorial labels;
- the output is a refined weight vector written back to `recommended_weights.py`, not a new model.

## Plain-English Summary

Simple version first.

The current system uses a fixed set of weights to combine ranking signals. L-BFGS (FR-018) tunes those weights using gradient descent on a mathematical loss function. That works, but gradient descent can get stuck in local optima and only uses one type of feedback.

FR-061 takes a different approach. It looks at real user behaviour from three sources:

1. **GSC**: "Users clicked link A but not link B when both appeared in search results" -- A is probably better than B.
2. **Matomo**: "Link A had a 12% click-through rate but link B had 3% in the same context" -- A is probably better.
3. **GA4**: "Users who followed link A stayed for 2 minutes but users who followed link B left in 5 seconds" -- A leads to more satisfying content.

Each of these observations creates a "preference pair" -- evidence that one link is better than another. FR-061 feeds thousands of these pairs into the RankBoost algorithm, which iteratively figures out which signals need more weight and which need less, based purely on what users actually do.

The key constraint: it never drops a signal entirely. Every signal keeps at least a small floor weight (0.01), so diagnostics and operator visibility are always maintained.

## Problem Statement

L-BFGS weight tuning (FR-018) has two limitations:

1. **Single feedback source**: it optimises on a differentiable proxy loss, not directly on real user behaviour data from multiple platforms.
2. **Gradient-based**: it can get trapped in local optima and has no mechanism to escape them. The resulting weights may be locally optimal but globally suboptimal.

FR-061 addresses both by using a boosting-based approach that:
- derives training signal from three independent user behaviour sources (GSC, Matomo, GA4);
- uses iterative feature-threshold selection which explores the weight space differently from gradient descent;
- produces weight adjustments that can be compared against L-BFGS tuning to identify cases where they disagree (which signals the operator to investigate).

## Goals

FR-061 should:

- construct pairwise preference pairs from GSC click data, Matomo CTR, and GA4 session duration;
- run T=200 rounds of AdaBoost-style boosting on those pairs;
- select the best feature-threshold weak ranker per round;
- accumulate importance coefficients (alpha_t) per signal;
- convert accumulated coefficients into weight adjustments with a floor of w_min=0.01;
- output the refined weight vector for operator review before applying;
- keep the optimisation off by default until an operator reviews the suggested weights;
- never drop a signal entirely (weights-only mode);
- fit the current Django + Celery + PostgreSQL architecture.

## Non-Goals

FR-061 does not:

- drop or disable any ranking signal -- all signals maintain a floor weight;
- replace L-BFGS tuning -- it provides a complementary optimisation that the operator can choose;
- modify the ranking pipeline at inference time -- it only adjusts the weight vector offline;
- create new signals or features;
- use editor labels (that is FR-060's domain);
- require real-time model serving;
- implement production code in the spec pass.

## Math-Fidelity Note

### Pairwise preference construction

From GSC:

```text
For each query where link A was clicked and link B was shown-not-clicked:
  add preference pair (A > B)
```

From Matomo:

```text
For each context where link A had higher CTR than link B:
  add preference pair (A > B)
```

From GA4:

```text
For each pair where link A had longer session duration than link B:
  add preference pair (A > B)
```

### RankBoost algorithm

**Initialise pair weights:**

```text
D_1(u, v) = 1 / |pairs|    for all pairs (u > v)
```

**Round t = 1..T (T=200):**

```text
For each feature f and threshold theta:
  r_t = SUM_{u>v} D_t(u,v) * ( [[f(u) > theta]] - [[f(v) > theta]] )

h_t = argmax_{f, theta} |r_t|      [best weak ranker this round]

alpha_t = 0.5 * ln((1 + r_t) / (1 - r_t))

D_{t+1}(u,v) = D_t(u,v) * exp(-alpha_t * ( [[h_t(u) > theta]] - [[h_t(v) > theta]] ))
Normalise D_{t+1} so it sums to 1
```

Here `[[ ]]` denotes the Iverson bracket (1 if true, 0 if false). Each round finds the single feature-threshold pair that best discriminates correctly ordered pairs from incorrectly ordered ones, then upweights the misranked pairs so the next round focuses on harder cases.

### Weight update (weights-only mode)

```text
For signal i:
  delta_i = SUM_t alpha_t * [[h_t selects feature i]] * sign(r_t)

  w_i <- max(w_min, w_i + eta * delta_i)
```

where `w_min = 0.01` (floor weight, never zero), `eta = 0.1` (learning rate, conservative).

The delta accumulates how often and how strongly each signal was selected as the best discriminator across all boosting rounds. Signals that frequently separate good links from bad links get larger positive deltas; signals that are rarely discriminative get near-zero deltas (but keep their floor weight).

### Output

```text
Updated weight vector: w = (w_1, ..., w_d) where w_i >= 0.01 for all i
```

This vector is written to a staging area for operator review. It is not applied automatically.

## Scope Boundary Versus Existing Signals

FR-061 must stay separate from:

- `L-BFGS weight tuning (FR-018)`
  - L-BFGS uses gradient descent on a differentiable loss;
  - FR-061 uses boosting rounds on pairwise preferences;
  - different optimisation paradigm, same output format (weight vector);
  - they should produce comparable but not identical weight vectors.

- `ListNet listwise ranking (FR-060)`
  - ListNet trains a tree-based model on editor labels;
  - FR-061 adjusts the linear weight vector on user behaviour data;
  - different training data sources, different model types.

- `Feedback UCB reranking (FR-013)`
  - UCB uses explore/exploit on individual arms at inference time;
  - FR-061 adjusts weights offline using historical behaviour data;
  - different timing, different mechanism.

Hard rule: FR-061 must not modify any signal computation, any model file, or any inference-time pipeline code. It only adjusts the weight vector.

## Inputs Required

FR-061 uses only data already ingested:

- GSC click/impression data per destination page (from `search_console` app)
- Matomo per-suggestion CTR (from `matomo` app)
- GA4 session engagement metrics per destination page (from `analytics` app)
- Current weight vector from `recommended_weights.py`
- All `score_*` fields on `Suggestion` for feature values

Explicitly disallowed FR-061 inputs:

- editor labels (reserved for FR-060)
- embedding vectors directly
- any data requiring new ingestion pipelines

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `rankboost.enabled`
- `rankboost.boosting_rounds`
- `rankboost.learning_rate`
- `rankboost.min_preference_pairs`
- `rankboost.floor_weight`
- `rankboost.auto_apply`

Defaults:

- `enabled = true`
- `boosting_rounds = 200`
- `learning_rate = 0.1`
- `min_preference_pairs = 500`
- `floor_weight = 0.01`
- `auto_apply = false`

Bounds:

- `50 <= boosting_rounds <= 1000`
- `0.01 <= learning_rate <= 0.5`
- `100 <= min_preference_pairs <= 10000`
- `0.001 <= floor_weight <= 0.05`

### Feature-flag behavior

- `enabled = false`
  - skip RankBoost computation entirely
  - store `rankboost_state = disabled`
- `enabled = true` and `auto_apply = false`
  - compute suggested weights, store in diagnostics for operator review
  - do not apply to live ranking
- `enabled = true` and `auto_apply = true`
  - compute and apply suggested weights after operator has reviewed at least one round

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `RankBoostDiagnostics` (stored as a system-level record, not per-suggestion)

Required fields:

- `rankboost_state` -- `computed`, `disabled`, `insufficient_pairs`
- `suggested_weights` -- the full weight vector produced by RankBoost
- `current_weights` -- the weight vector before adjustment
- `weight_deltas` -- per-signal change (positive = increase, negative = decrease)
- `total_preference_pairs` -- number of pairs used for training
- `pairs_by_source` -- breakdown: `{gsc: N, matomo: N, ga4: N}`
- `top_weak_rankers` -- top 10 feature-threshold pairs selected by boosting
- `rounds_completed` -- number of boosting rounds that ran
- `pairwise_accuracy` -- fraction of preference pairs correctly ordered by the suggested weights
- `model_version` -- timestamp of the computation

Plain-English review helper text should say:

- `RankBoost suggests adjusting signal weights based on what users actually clicked and engaged with.`
- `Weight increases mean users responded better to links that scored high on that signal.`
- `Weight decreases mean that signal was not a strong predictor of user preference.`

## Storage / Model / API Impact

### System-level model

- No per-suggestion storage needed -- FR-061 operates on weights, not scores.
- Store the latest `RankBoostDiagnostics` as a JSON record in `AppSetting` or a dedicated model.

### Weight staging

- Suggested weights stored in `AppSetting` key `rankboost.suggested_weights`
- Operator reviews and either applies or discards
- History of past suggestions stored for comparison

### PipelineRun snapshot

Add FR-061 state to `PipelineRun.config_snapshot` (whether RankBoost weights are active, which version).

### Backend API

Add:

- `GET /api/settings/rankboost/`
- `PUT /api/settings/rankboost/`
- `POST /api/settings/rankboost/run/` -- triggers manual optimisation
- `POST /api/settings/rankboost/apply/` -- applies suggested weights to live system
- `GET /api/settings/rankboost/diagnostics/` -- returns latest diagnostics

### Review / admin / frontend

Add one settings card:

- enabled toggle
- boosting rounds slider
- learning rate input
- minimum pairs threshold
- floor weight input
- auto-apply toggle (with warning)
- "Run Now" button
- weight comparison table (current vs. suggested vs. delta)

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/rankboost_optimizer.py` -- new service file
- `backend/apps/pipeline/tasks.py` -- add periodic optimisation task
- `backend/apps/suggestions/recommended_weights.py` -- update hook for applying weights
- `backend/apps/core/views.py` -- add settings and diagnostics endpoints
- `backend/apps/api/urls.py` -- wire new endpoints
- `backend/apps/pipeline/tests.py` -- FR-061 unit tests
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched:

- `backend/apps/pipeline/services/ranker.py` -- no inference-time changes
- All individual signal computation files
- `backend/apps/content/models.py`
- `backend/apps/suggestions/models.py` -- no per-suggestion fields needed

## Test Plan

### 1. Preference pair construction

- GSC data with click/no-click produces valid pairs
- Matomo CTR differences produce valid pairs
- GA4 session duration differences produce valid pairs
- pairs from all three sources are combined correctly

### 2. Boosting rounds

- 200 rounds complete without error on valid input
- each round selects a different or same feature-threshold pair
- alpha coefficients are finite and non-zero

### 3. Weight floor enforcement

- no signal weight falls below `w_min = 0.01`
- signals with zero alpha still retain floor weight

### 4. Insufficient data

- fewer than `min_preference_pairs` pairs -> state `insufficient_pairs`, no weights suggested

### 5. Weight application

- `auto_apply = false` -> weights stored but not applied
- `auto_apply = true` -> weights applied to `recommended_weights.py` after operator review

### 6. Pairwise accuracy

- suggested weights achieve higher pairwise accuracy than current weights on held-out pairs

### 7. Isolation

- running FR-061 does not modify any `Suggestion` row
- running FR-061 does not modify any signal computation

### 8. Snapshot coverage

- `PipelineRun.config_snapshot` records whether RankBoost weights are active

## Rollout Plan

### Step 1 -- diagnostics only

- run RankBoost with `auto_apply = false`
- inspect suggested weights vs. current weights
- verify preference pairs look sensible

### Step 2 -- operator comparison

- compare RankBoost suggestions against L-BFGS suggestions
- investigate signals where they disagree
- test suggested weights on a shadow pipeline run

### Step 3 -- optional application

- only after operator verification passes
- apply suggested weights and monitor ranking quality metrics

## Risk List

- noisy preference pairs from low-traffic pages -- mitigated by `min_preference_pairs` threshold and Laplace smoothing on CTR;
- GSC/Matomo/GA4 data may have different biases (position bias, device bias) -- mitigated by treating each source as an independent set of pairs rather than mixing raw metrics;
- the floor weight constraint means RankBoost cannot express "this signal is harmful" -- this is intentional, as the operator should make that decision explicitly;
- auto-apply mode could degrade ranking if the behaviour data is misleading -- mitigated by defaulting `auto_apply = false` and requiring operator review.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"rankboost.enabled": "true",
"rankboost.boosting_rounds": "200",
"rankboost.learning_rate": "0.1",
"rankboost.min_preference_pairs": "500",
"rankboost.floor_weight": "0.01",
"rankboost.auto_apply": "false",
```

**Why these values:**

- `enabled = true` -- compute suggested weights from day one for operator review.
- `boosting_rounds = 200` -- sufficient to converge on most datasets without overfitting.
- `learning_rate = 0.1` -- conservative to prevent large weight swings from noisy data.
- `min_preference_pairs = 500` -- requires meaningful behaviour data volume before suggesting changes.
- `floor_weight = 0.01` -- ensures every signal remains active for diagnostics.
- `auto_apply = false` -- operator must review before any weight change goes live.

### Migration note

FR-061 must ship a new data migration that upserts these six keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
