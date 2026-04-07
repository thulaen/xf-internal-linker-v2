# FR-060 - ListNet Listwise Ranking

## Confirmation

- **Backlog confirmed**: `FR-060 - ListNet Listwise Ranking` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No listwise ranking model exists in the current system. The closest existing mechanism is L-BFGS weight tuning (FR-018), which optimises scalar weights via gradient descent on a proxy loss. FR-060 learns from entire ranked lists using the Plackett-Luce distribution -- a fundamentally different mathematical framework.
- **Repo confirmed**: Editor approval/rejection data is already stored per suggestion batch. The `Suggestion` model tracks `status` (approved/rejected) grouped by `pipeline_run`, providing the training labels needed for listwise learning.

## Current Repo Map

### Weight tuning already available

- `backend/apps/pipeline/services/ranker.py`
  - `_calculate_composite_scores_full_batch_py(...)` -- computes a weighted sum of all ranking signals. The weights are scalar multipliers tuned by L-BFGS or set manually.
  - The weighted sum treats each suggestion independently (pointwise). It cannot learn that "link A is better than link B given that both appeared in the same batch."

- `backend/apps/suggestions/recommended_weights.py`
  - `RECOMMENDED_PRESET_WEIGHTS` -- stores the current weight vector. FR-060 would produce an alternative scoring function that supplements or replaces this linear combination.

### Training data already available

- `backend/apps/suggestions/models.py`
  - `Suggestion` rows with `status` in {approved, rejected, pending} grouped by `pipeline_run_id` and `host_content_item_id`. Each group is one "query" in listwise terms.
  - Feature vectors per suggestion: `score_semantic`, `score_keyword`, `score_authority`, plus all signal-specific fields.

### LightGBM integration pattern

- `backend/requirements.txt` -- LightGBM is not currently installed. FR-060 adds it as a new dependency.
- The LightGBM `rank:ndcg` objective natively implements the ListNet loss function and handles the Plackett-Luce gradient computation internally.

## Source Summary

### Patent: US7734633B2 -- Listwise Ranking (Microsoft, 2010)

**Plain-English description of the patent:**

The patent describes a method for training a ranking function by comparing entire ordered lists of documents rather than individual document pairs or single documents. It defines a probability distribution over all possible orderings of a list (the Plackett-Luce model), then minimises the cross-entropy between the predicted ordering distribution and the ground-truth ordering distribution.

**Repo-safe reading:**

The patent targets web search ranking with millions of queries. This repo operates at a smaller scale (thousands of suggestion batches) but the mathematical framework applies identically. The Plackett-Luce top-1 approximation used here reduces computational cost from factorial to linear while preserving the listwise learning signal.

**What is directly supported by the patent:**

- defining a probability distribution over ranked lists using the Plackett-Luce model;
- computing loss as the cross-entropy between model and truth distributions;
- optimising ranking quality directly via listwise gradients.

**What is adapted for this repo:**

- "queries" map to (source_page, batch_id) groups of suggestions;
- "relevance grades" map to editor approval status (approved = high, rejected = low, pending = excluded);
- the patent describes a custom neural network; this repo uses LightGBM with `rank:ndcg` objective, which implements the same gradient formula internally;
- the output is used as an additive scoring adjustment, not a full replacement of the existing weighted sum.

## Plain-English Summary

Simple version first.

Right now the ranker scores each link suggestion on its own. It adds up weighted signals (semantic similarity, keyword match, authority, etc.) and produces a number. Two links from the same batch are scored independently -- the ranker does not consider how they compare to each other.

Editors, though, make decisions in context. They see a whole batch of suggestions for a page and approve the best ones while rejecting the worse ones. That relative judgment -- "A is better than B in this specific context" -- carries information that pointwise scoring throws away.

FR-060 learns from those relative decisions. It trains a model that says "given a batch of candidates with these features, this is the probability that each one should be ranked first." The model learns patterns like "when two candidates have similar semantic scores, the one with higher authority usually gets approved." These inter-item patterns are invisible to the current pointwise approach.

## Problem Statement

The current ranking system scores suggestions independently using a linear weighted sum of signals. This pointwise approach cannot capture:

1. **Inter-item dependencies**: the quality of link A depends on what other links are available for the same page. If A and B are semantically identical destinations, only one should rank high.
2. **Context-sensitive feature importance**: the signals that separate "great" from "good" may differ from those that separate "good" from "bad." A single weight vector cannot express this.
3. **List-level optimality**: the weighted sum optimises per-item accuracy, not the quality of the entire ranked list. A model that gets every item "almost right" may still produce a badly ordered list.

FR-060 addresses all three by training a listwise model that directly optimises NDCG (the standard measure of ranked-list quality) using editor feedback as training labels.

## Goals

FR-060 should:

- train a LightGBM model with `rank:ndcg` objective on editor-labelled suggestion batches;
- use the Plackett-Luce top-1 probability as the listwise loss function;
- produce a learned scoring function that captures inter-item feature interactions;
- output a score adjustment that is additive on top of the existing composite score;
- keep the model off by default (weight = 0.0) until operator validation;
- support retraining on a configurable schedule (default: weekly) via Celery task;
- persist the trained model as a serialised file, not in the database;
- fit the current Django + Celery + PostgreSQL architecture.

## Non-Goals

FR-060 does not:

- replace the existing weighted sum -- it supplements it with an additive adjustment;
- modify any individual signal computation (semantic, keyword, authority, etc.);
- require real-time model serving infrastructure (scoring is batch, not per-request);
- implement a custom neural network (LightGBM provides the gradient-boosted tree model);
- change the editor review UI or approval workflow;
- depend on analytics data (only editor labels are used);
- implement production code in the spec pass.

## Math-Fidelity Note

### Plackett-Luce top-1 probability

Let `s = (s_1, ..., s_n)` be the model's score vector for `n` candidates in one batch.

**Model distribution (softmax):**

```text
P_model(i | s) = exp(s_i) / SUM_j exp(s_j)
```

This gives the probability that candidate `i` would be ranked first according to the model.

**Truth distribution:**

```text
P_truth(i | y) = exp(y_i) / SUM_j exp(y_j)
```

where `y_i` is the relevance grade: `y = 3` for approved suggestions, `y = 1` for rejected, `y = 0` for excluded/pending.

**Cross-entropy loss:**

```text
L = -SUM_i P_truth(i | y) * log(P_model(i | s))
```

**Gradient with respect to each score:**

```text
dL/ds_i = P_model(i | s) - P_truth(i | y)
```

This gradient pushes the model's probability distribution toward the truth distribution. Approved items get their scores pushed up; rejected items get pushed down; the magnitude depends on how far the model is from the truth.

### LightGBM implementation

LightGBM with `objective='rank_xendcg'` implements exactly this loss function. Configuration:

```text
objective:        rank_xendcg
n_estimators:     500
num_leaves:       31
learning_rate:    0.05
min_data_in_leaf: 5
group:            suggestion batch sizes (e.g. [12, 8, 15, ...])
```

The `group` parameter tells LightGBM which suggestions belong to the same batch. Each batch is one "query" in learning-to-rank terms.

### Score integration

The trained model produces a raw score per candidate:

```text
listnet_raw = model.predict(feature_vector)
```

This is normalised to [0, 1] per batch:

```text
listnet_score = (listnet_raw - min(batch)) / (max(batch) - min(batch) + epsilon)
```

Then added to the composite score:

```text
score_final += listnet.ranking_weight * listnet_score
```

Default: `ranking_weight = 0.0` -- diagnostics run silently with no ranking impact.

### Feature vector

The input to the model is the same feature set used by the existing weighted sum:

```text
x_i = [score_semantic, score_keyword, score_authority, score_freshness,
       score_phrase_match, score_field_bm25, score_click_distance,
       score_feedback_ucb, score_information_gain, ...]
```

All currently computed signals are included. The model learns which combinations matter for list-level quality.

### Minimum training data requirement

ListNet requires sufficient labelled batches to generalise:

```text
min_batches = 50     (at least 50 suggestion batches with mixed approved/rejected)
min_items_per_batch = 3
```

If the training set is below this threshold, the model is not trained and the score falls back to neutral (0.5).

## Scope Boundary Versus Existing Signals

FR-060 must stay separate from:

- `L-BFGS weight tuning (FR-018)`
  - L-BFGS tunes scalar weights on a proxy loss (cross-entropy per item);
  - FR-060 trains a tree-based model on listwise loss (cross-entropy per list);
  - different optimisation target, different model class, different output format.

- `RRF fusion (FR-046)`
  - RRF is a fixed-formula rank fusion with no learning;
  - FR-060 is a learned listwise model;
  - they operate at different stages of the pipeline.

- `Feedback UCB reranking (FR-013)`
  - UCB uses explore/exploit on individual arms (independent suggestions);
  - FR-060 models inter-item dependencies within a batch;
  - orthogonal mechanisms.

- `MMR diversity reranking (FR-015)`
  - MMR is a post-hoc diversity heuristic applied after scoring;
  - FR-060 is a learned scoring model applied during scoring;
  - different pipeline stages, different purposes.

Hard rule: FR-060 must not modify any individual signal value. It reads feature vectors as input and produces one additive adjustment per suggestion.

## Inputs Required

FR-060 uses only data already available in the pipeline:

- `Suggestion.status` -- editor approval labels (approved/rejected)
- `Suggestion.pipeline_run_id` + `Suggestion.host_content_item_id` -- batch grouping
- All `score_*` fields on `Suggestion` -- the feature vector
- `PipelineRun.config_snapshot` -- for reproducibility

Explicitly disallowed FR-060 inputs:

- raw analytics data (GA4, GSC, Matomo) -- editor labels only
- embedding vectors directly (only the pre-computed similarity scores)
- any data not already stored on the `Suggestion` model

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `listnet.enabled`
- `listnet.ranking_weight`
- `listnet.min_training_batches`
- `listnet.retrain_interval_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `min_training_batches = 50`
- `retrain_interval_days = 7`

Bounds:

- `0.0 <= ranking_weight <= 0.15`
- `20 <= min_training_batches <= 500`
- `1 <= retrain_interval_days <= 30`

### Feature-flag behavior

- `enabled = false`
  - skip model inference entirely
  - store `score_listnet = 0.5`
  - store `listnet_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - run model inference and store diagnostics
  - do not change ranking order
- `enabled = true` and insufficient training data
  - store `score_listnet = 0.5`
  - store `listnet_state = neutral_insufficient_data`

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.listnet_diagnostics`

Required fields:

- `score_listnet` -- model output normalised to [0, 1]
- `listnet_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_insufficient_data`
  - `neutral_model_not_found`
  - `neutral_processing_error`
- `listnet_raw_score` -- raw model output before normalisation
- `batch_rank` -- position within the batch according to the model
- `batch_size` -- number of candidates in this batch
- `model_version` -- timestamp of the model file used
- `training_batches_used` -- how many batches the model was trained on
- `top_feature_importances` -- top 5 features by LightGBM split importance

Plain-English review helper text should say:

- `ListNet score means this suggestion was ranked by a model that learned from editor decisions on similar batches.`
- `A high score means the model predicts this link would be approved by editors based on patterns in past approvals.`
- `Neutral means the model has not been trained yet or the feature is disabled.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_listnet: FloatField(default=0.5)`
- `listnet_diagnostics: JSONField(default=dict, blank=True)`

### Model file storage

- Trained LightGBM model serialised to `backend/ml_models/listnet_latest.lgbm`
- Previous model kept as `listnet_previous.lgbm` for rollback
- Model file size: ~50-100 MB depending on training data volume

### PipelineRun snapshot

Add FR-060 settings and model version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/listnet/`
- `PUT /api/settings/listnet/`
- `POST /api/settings/listnet/retrain/` -- triggers manual retraining

### Celery task

Add:

- `train_listnet_model` -- periodic task running every `retrain_interval_days`
- Reads all labelled suggestions, builds training set, trains model, saves to disk

### Review / admin / frontend

Add one new review row:

- `ListNet Score`

Add one small diagnostics block:

- model score and batch rank
- model version and training size
- top feature importances
- neutral reason when fallback was used

Add one settings card:

- enabled toggle
- ranking weight slider
- minimum training batches
- retrain interval selector
- manual retrain button

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/listnet_ranker.py` -- new service file
- `backend/apps/pipeline/services/ranker.py` -- add FR-060 additive hook
- `backend/apps/pipeline/tasks.py` -- add periodic training task
- `backend/apps/suggestions/models.py` -- add two new fields
- `backend/apps/suggestions/serializers.py` -- expose new fields
- `backend/apps/suggestions/views.py` -- snapshot FR-060 settings
- `backend/apps/suggestions/admin.py` -- expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` -- add settings endpoint
- `backend/apps/api/urls.py` -- wire new settings endpoint
- `backend/apps/pipeline/tests.py` -- FR-060 unit tests
- `backend/requirements.txt` -- add LightGBM dependency
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched in the FR-060 implementation pass:

- All individual signal computation files (semantic, keyword, authority, etc.)
- `backend/apps/content/models.py` -- no new content fields
- `backend/apps/graph/models.py` -- no new graph edges
- `backend/apps/pipeline/services/phrase_matching.py`
- `backend/apps/pipeline/services/learned_anchor.py`

## Test Plan

### 1. Model training

- with 50+ labelled batches, model trains successfully and saves to disk
- with fewer than `min_training_batches`, model is not trained and state is `neutral_insufficient_data`
- retraining with new data produces a different model version

### 2. Score computation

- model output is normalised to [0, 1] per batch
- identical feature vectors within a batch produce identical scores
- different batches produce independently normalised scores

### 3. Neutral fallback cases

- model file missing -> `score = 0.5`, state `neutral_model_not_found`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`
- insufficient training data -> `score = 0.5`, state `neutral_insufficient_data`

### 4. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 5. Bounded score

- score is always in [0.5, 1.0] mapped range regardless of input
- no suggestion produces a score below 0.0 or above 1.0 in raw form

### 6. Isolation from other signals

- changing any individual signal weight does not affect `score_listnet`
- the model reads feature values but never writes to them

### 7. Serializer and frontend contract

- `score_listnet` and `listnet_diagnostics` appear in suggestion detail API response
- review dialog renders the `ListNet Score` row
- settings page loads and saves FR-060 settings

### 8. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-060 settings and model version

## Rollout Plan

### Step 1 -- training and diagnostics only

- train the ListNet model with `ranking_weight = 0.0`
- verify model scores correlate with editor approval patterns
- inspect feature importances for sanity

### Step 2 -- operator review

- compare model rankings against editor decisions on held-out batches
- confirm NDCG improvement over the baseline weighted sum
- check for overfitting by comparing train vs. validation metrics

### Step 3 -- optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.03` to `0.05`

## Risk List

- overfitting on small training sets -- mitigated by `min_training_batches` threshold and LightGBM's built-in regularisation (num_leaves=31, min_data_in_leaf=5);
- model staleness if editors change their criteria -- mitigated by periodic retraining;
- LightGBM dependency adds ~100 MB to the Docker image -- acceptable given the value;
- model file corruption could break scoring -- mitigated by keeping a previous model for rollback and falling back to neutral on load failure;
- batch size variance (some batches have 5 items, others 50) may bias training -- mitigated by LightGBM's group-aware training that handles variable-length groups natively.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"listnet.enabled": "true",
"listnet.ranking_weight": "0.04",
"listnet.min_training_batches": "50",
"listnet.retrain_interval_days": "7",
```

**Why these values:**

- `enabled = true` -- run diagnostics from day one so the operator can inspect model quality before enabling ranking impact.
- `ranking_weight = 0.04` -- conservative starting point. The listwise model captures inter-item patterns invisible to the pointwise sum, but it needs validation on live data before receiving significant weight.
- `min_training_batches = 50` -- ensures the model has seen enough diversity to generalise. Below 50 batches the model is likely to memorise rather than learn patterns.
- `retrain_interval_days = 7` -- weekly retraining balances freshness against compute cost.

### Migration note

FR-060 must ship a new data migration that upserts these four keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
