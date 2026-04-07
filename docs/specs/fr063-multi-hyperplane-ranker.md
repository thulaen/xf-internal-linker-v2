# FR-063 - Multi-Hyperplane Ranker Ensemble

## Confirmation

- **Backlog confirmed**: `FR-063 - Multi-Hyperplane Ranker Ensemble` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No grade-pair-specific ranking model exists in the current system. The closest mechanism is the single weighted scoring function in `ranker.py`, which applies one weight vector to all quality levels. FR-063 trains separate SVM models for each pair of relevance grades, capturing the insight that the features separating "great from good" differ from those separating "good from bad."
- **Repo confirmed**: Editor-labelled suggestions with graded quality levels are available. The `Suggestion.status` field provides binary labels (approved/rejected), and the review workflow can be extended to support finer grades (perfect/good/marginal/bad).

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `_calculate_composite_scores_full_batch_py(...)` -- single weighted sum with one weight vector for all candidates regardless of quality level.
  - All candidates pass through the same linear combination. A suggestion that is "almost perfect" and one that is "borderline acceptable" are scored by identical feature weights.

### Training data already available

- `backend/apps/suggestions/models.py`
  - `Suggestion.status` -- currently binary (approved/rejected). FR-063 requires 4-grade labels.
  - `Suggestion` feature vector: all `score_*` fields (~50 features total).
  - Grouped by `pipeline_run_id` for batch context.

### scikit-learn pattern

- `backend/requirements.txt` -- scikit-learn is already installed (used by isotonic regression and other ML utilities).
- `sklearn.svm.LinearSVC` provides the linear SVM implementation needed for each grade-pair model.

## Source Summary

### Patent: US8122015B2 -- Multi-Ranker For Search (Microsoft, 2012)

**Plain-English description of the patent:**

The patent describes training multiple ranking models, one for each pair of relevance grades, then combining their outputs via rank aggregation. For K relevance grades, K(K-1)/2 separate models are trained, each specialised in distinguishing one quality level from another. The final ranking is produced by aggregating the per-model rankings using BordaCount or similar voting schemes.

**Repo-safe reading:**

The patent uses neural networks for each ranker. This repo uses linear SVMs (much cheaper, ~200x less RAM) since the feature space is modest (~50 features) and linear boundaries are sufficient for the quality distinctions needed.

**What is directly supported by the patent:**

- training separate models per relevance-grade pair;
- BordaCount aggregation across per-pair rankings;
- the insight that different grade-pair boundaries require different feature weights.

**What is adapted for this repo:**

- 4 grades (perfect/good/marginal/bad) producing 6 grade pairs;
- linear SVMs instead of neural networks;
- feature vectors from existing suggestion scores, not raw document features;
- output as an additive score adjustment, not a full ranking replacement.

## Plain-English Summary

Simple version first.

Think of a hiring panel. One interviewer is great at telling apart outstanding candidates from good ones -- they focus on leadership and vision. Another interviewer is better at filtering out weak candidates -- they focus on basic skills and communication.

The current ranker is like having just one interviewer with one checklist for everyone. It cannot adapt its criteria based on what quality distinction it is making.

FR-063 trains six specialised "interviewers" (SVM models), one for each pair of quality levels:

1. Perfect vs. Good -- what makes a suggestion outstanding, not just acceptable?
2. Perfect vs. Marginal -- what separates the best from the mediocre?
3. Perfect vs. Bad -- what separates the best from the worst?
4. Good vs. Marginal -- what makes an acceptable suggestion better than a borderline one?
5. Good vs. Bad -- what separates acceptable from clearly wrong?
6. Marginal vs. Bad -- what makes a borderline suggestion still better than a bad one?

Each model learns different feature weights. For example, the "Perfect vs. Good" model might weight anchor precision heavily (the best suggestions have precise anchors), while the "Good vs. Bad" model might weight basic semantic relevance (bad suggestions are off-topic).

The six models each rank the candidates, then their rankings are combined by voting (BordaCount). A suggestion that many models rank highly gets a high final score.

## Problem Statement

The current single-weight-vector scoring function applies identical feature importance to all quality distinctions. This causes two problems:

1. **Undifferentiated quality thresholds**: the features that push a suggestion from "bad" to "marginal" (basic topical relevance) differ from those that push it from "good" to "perfect" (anchor precision, passage alignment). One weight vector cannot express both.
2. **Grade compression**: with a single linear function, suggestions of different quality levels get compressed into a narrow score range, making it harder to distinguish between them.

FR-063 addresses both by learning quality-level-specific feature weights and aggregating via voting, which naturally spreads out the score distribution.

## Goals

FR-063 should:

- train 6 LinearSVC models, one per grade pair from 4 relevance grades;
- use BordaCount aggregation to combine per-model rankings into a single score;
- produce a normalised score in [0, 1] that reflects multi-model consensus;
- support grade labels from extended review workflow (perfect/good/marginal/bad);
- fall back to binary labels (approved->good, rejected->bad) when fine-grained labels are unavailable;
- keep the score additive on top of existing ranking, off by default (weight = 0.0);
- retrain periodically (default: weekly) via Celery task;
- fit the current Django + Celery + PostgreSQL + scikit-learn architecture.

## Non-Goals

FR-063 does not:

- replace the existing weighted sum -- it supplements it;
- modify the editor review UI to add grade labels (that is a prerequisite but separate work);
- use non-linear SVMs (linear is sufficient and much cheaper);
- create new features -- it operates on existing score_* fields;
- require GPU or significant RAM at inference time;
- implement production code in the spec pass.

## Math-Fidelity Note

### Grade definitions

```text
G = {bad=0, marginal=1, good=2, perfect=3}
```

When fine-grained labels are unavailable, map: `approved -> good (2)`, `rejected -> bad (0)`, which produces C(2,2) = 1 grade pair (degenerate case, equivalent to a single binary SVM).

### Grade-pair SVM training

```text
Grade pairs: C(4,2) = 6 pairs: (3,2), (3,1), (3,0), (2,1), (2,0), (1,0)

For each pair (a, b) where a > b:
  Positive examples: items labelled grade a  ->  y = +1
  Negative examples: items labelled grade b  ->  y = -1
  Train: LinearSVC(C=1.0, max_iter=2000)
    f_{ab}(x) = w_{ab} . x + b_{ab}     [x in R^d, d = ~50 features]
```

Each model `f_{ab}` learns a hyperplane that best separates items of grade `a` from items of grade `b`. The weight vector `w_{ab}` reveals which features matter most for that specific quality distinction.

### BordaCount aggregation

For each candidate `x` in a batch of `n` candidates:

```text
For each of the 6 grade-pair models:
  rank_{ab}(x) = position of x when all n candidates are sorted by f_{ab}(x) descending
                 (rank 1 = highest score)

borda_score(x) = SUM_{all 6 pairs} (n - rank_{ab}(x))
```

A candidate ranked 1st by a model contributes `(n - 1)` Borda points; ranked last contributes 0. The sum across all 6 models measures consensus.

### Normalised output

```text
max_borda = 6 * (n - 1)     [maximum possible Borda score]
mhr_score = borda_score(x) / max_borda     [normalised to [0, 1]]
```

### Score integration

```text
score_final += mhr.ranking_weight * (mhr_score - 0.5) * 2
```

This centers the adjustment around zero: an average candidate (mhr_score = 0.5) gets no adjustment; a top candidate (mhr_score near 1.0) gets a positive boost; a bottom candidate gets a negative push.

Default: `ranking_weight = 0.0` -- diagnostics run silently.

### RAM and compute budget

```text
Training: 6 SVMs x ~50 features x 4 bytes = negligible weight storage
          Training workspace: ~200 MB (discardable after training)
Inference: 6 dot products per candidate = negligible compute
           Sorting n candidates 6 times = O(6 * n * log(n))
```

## Scope Boundary Versus Existing Signals

FR-063 must stay separate from:

- `Single weighted scorer (ranker.py)`
  - the weighted sum uses one weight vector for all quality levels;
  - FR-063 uses 6 different weight vectors, one per grade pair;
  - different mathematical structure, complementary outputs.

- `ListNet listwise ranking (FR-060)`
  - ListNet learns a single tree-based model from list permutations;
  - FR-063 learns 6 linear models from grade-pair comparisons;
  - different model types, different training signals.

- `RankBoost weight optimisation (FR-061)`
  - RankBoost adjusts the single weight vector offline;
  - FR-063 trains separate models, not a single weight vector;
  - different outputs and different mechanisms.

- `L-BFGS weight tuning (FR-018)`
  - L-BFGS tunes one weight vector via gradient descent;
  - FR-063 trains 6 SVMs and aggregates via BordaCount;
  - fundamentally different architecture.

Hard rule: FR-063 must not modify any signal computation or any other model's training data. It reads feature vectors and labels, trains its own models, and produces one additive score per suggestion.

## Inputs Required

FR-063 uses only data already available:

- `Suggestion.status` or extended grade label -- quality level per suggestion
- All `score_*` fields on `Suggestion` -- the feature vector (~50 features)
- `Suggestion.pipeline_run_id` + `Suggestion.host_content_item_id` -- batch grouping for rank computation

Explicitly disallowed inputs:

- raw text or embeddings (only pre-computed score features)
- analytics data directly (that is FR-061's domain)
- any data not already stored on the `Suggestion` model

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `mhr.enabled`
- `mhr.ranking_weight`
- `mhr.svm_regularisation`
- `mhr.min_labelled_items`
- `mhr.retrain_interval_days`

Defaults:

- `enabled = true`
- `ranking_weight = 0.0`
- `svm_regularisation = 1.0`
- `min_labelled_items = 100`
- `retrain_interval_days = 7`

Bounds:

- `0.0 <= ranking_weight <= 0.15`
- `0.01 <= svm_regularisation <= 10.0`
- `30 <= min_labelled_items <= 1000`
- `1 <= retrain_interval_days <= 30`

### Feature-flag behavior

- `enabled = false`
  - skip model inference entirely
  - store `score_mhr = 0.5`
  - store `mhr_state = neutral_feature_disabled`
- `enabled = true` and `ranking_weight = 0.0`
  - run model inference and store diagnostics
  - do not change ranking order
- `enabled = true` and insufficient labels
  - store `score_mhr = 0.5`
  - store `mhr_state = neutral_insufficient_labels`

## Diagnostics And Explainability Plan

Add one new diagnostics object:

- `Suggestion.mhr_diagnostics`

Required fields:

- `score_mhr` -- BordaCount-normalised score in [0, 1]
- `mhr_state`
  - `computed`
  - `neutral_feature_disabled`
  - `neutral_insufficient_labels`
  - `neutral_model_not_found`
  - `neutral_binary_fallback` (only 2 grades available, 1 model instead of 6)
  - `neutral_processing_error`
- `per_model_ranks` -- dictionary mapping each grade pair to this suggestion's rank
- `borda_score_raw` -- raw Borda points before normalisation
- `batch_size` -- number of candidates in this batch
- `grade_pair_weights` -- per-model top 3 feature importances (SVM coefficients)
- `model_version` -- timestamp of the trained model set

Plain-English review helper text should say:

- `MHR score reflects how consistently this suggestion ranks highly across six quality-level comparisons.`
- `A high score means multiple specialised models agree this is a strong suggestion.`
- `Per-model ranks show which quality distinctions this suggestion wins or loses.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `score_mhr: FloatField(default=0.5)`
- `mhr_diagnostics: JSONField(default=dict, blank=True)`

### Model file storage

- 6 serialised LinearSVC models in `backend/ml_models/mhr_models/`
- One file per grade pair: `svm_3v2.pkl`, `svm_3v1.pkl`, etc.
- Total size: < 1 MB (linear SVMs are tiny)

### PipelineRun snapshot

Add FR-063 settings and model version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/mhr/`
- `PUT /api/settings/mhr/`
- `POST /api/settings/mhr/retrain/` -- triggers manual retraining

### Review / admin / frontend

Add one new review row:

- `MHR Score`

Add one small diagnostics block:

- BordaCount score and per-model ranks
- grade-pair feature importances
- model version and label count

Add one settings card:

- enabled toggle
- ranking weight slider
- SVM regularisation input
- minimum labels threshold
- retrain interval selector
- manual retrain button

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/mhr_ranker.py` -- new service file
- `backend/apps/pipeline/services/ranker.py` -- add FR-063 additive hook
- `backend/apps/pipeline/tasks.py` -- add periodic training task
- `backend/apps/suggestions/models.py` -- add two new fields
- `backend/apps/suggestions/serializers.py` -- expose new fields
- `backend/apps/suggestions/views.py` -- snapshot FR-063 settings
- `backend/apps/suggestions/admin.py` -- expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` -- add settings endpoint
- `backend/apps/api/urls.py` -- wire new endpoints
- `backend/apps/pipeline/tests.py` -- FR-063 unit tests
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

### 1. Model training (4-grade labels)

- 6 models train successfully when all 4 grade levels are represented
- each model has different weight vectors (not identical)
- models save to disk and reload correctly

### 2. Model training (binary fallback)

- with only approved/rejected labels, 1 model trains instead of 6
- state is `neutral_binary_fallback`, score still computed

### 3. BordaCount aggregation

- candidate ranked 1st by all 6 models gets maximum Borda score
- candidate ranked last by all 6 models gets minimum Borda score
- normalised score is in [0, 1]

### 4. Neutral fallback cases

- model files missing -> `score = 0.5`, state `neutral_model_not_found`
- feature disabled -> `score = 0.5`, state `neutral_feature_disabled`
- insufficient labels -> `score = 0.5`, state `neutral_insufficient_labels`

### 5. Ranking off by default

- `ranking_weight = 0.0` -> final score ordering unchanged

### 6. Isolation

- training and inference do not modify any `score_*` field on Suggestion
- MHR does not read or write to any other model's file

### 7. Snapshot coverage

- `PipelineRun.config_snapshot` includes FR-063 settings and model version

## Rollout Plan

### Step 1 -- training and diagnostics only

- train MHR with `ranking_weight = 0.0`
- inspect per-model feature importances for each grade pair
- verify that different grade pairs produce meaningfully different weight vectors

### Step 2 -- operator review

- compare MHR rankings against editor decisions on held-out data
- check whether MHR disagrees with the weighted sum on interesting cases
- confirm BordaCount scores correlate with approval rates

### Step 3 -- optional small ranking enablement

- only after operator verification passes
- recommended first live weight: `0.03` to `0.05`

## Risk List

- fine-grained grade labels (4 levels) may not be available initially -- mitigated by binary fallback mode;
- small training sets per grade pair may cause overfitting -- mitigated by linear SVMs (low capacity) and `svm_regularisation` parameter;
- BordaCount treats all 6 models equally, but some grade distinctions may be more important -- future work could weight the models;
- the binary fallback (1 model, no BordaCount) provides less value than the full 6-model version -- the operator should understand this distinction.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"mhr.enabled": "true",
"mhr.ranking_weight": "0.04",
"mhr.svm_regularisation": "1.0",
"mhr.min_labelled_items": "100",
"mhr.retrain_interval_days": "7",
```

**Why these values:**

- `enabled = true` -- start training and diagnostics from day one.
- `ranking_weight = 0.04` -- conservative; MHR captures grade-specific patterns but needs validation.
- `svm_regularisation = 1.0` -- scikit-learn default, good balance between fit and generalisation.
- `min_labelled_items = 100` -- ensures at least ~25 items per grade level on average.
- `retrain_interval_days = 7` -- weekly retraining as new labels arrive.

### Migration note

FR-063 must ship a new data migration that upserts these five keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
