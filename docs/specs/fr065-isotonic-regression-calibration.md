# FR-065 - Isotonic Regression Score Calibration

## Confirmation

- **Backlog confirmed**: `FR-065 - Isotonic Regression Score Calibration` is a pending request in `FEATURE-REQUESTS.md`.
- **Repo confirmed**: No score calibration layer exists in the current system. The closest mechanism is Wilson score intervals (FR-023), which compute binomial confidence intervals on click rates. FR-065 transforms arbitrary composite ranking scores into calibrated probabilities via isotonic regression -- a fundamentally different purpose (probability calibration, not confidence estimation).
- **Repo confirmed**: scikit-learn is already installed and provides `IsotonicRegression` which implements the Pool Adjacent Violators (PAV) algorithm. The training data (composite scores paired with binary editor approval outcomes) is already available from the `Suggestion` model.

## Current Repo Map

### Scoring already available

- `backend/apps/pipeline/services/ranker.py`
  - `score_final` -- composite ranking score per suggestion. Currently on an arbitrary scale that varies across source pages and pipeline runs. A score of 0.75 on one page does not mean the same thing as 0.75 on another page.

- `backend/apps/suggestions/models.py`
  - `Suggestion.score_final` -- the raw composite score.
  - `Suggestion.status` -- editor approval label (approved/rejected). Paired with `score_final`, these form the training data for calibration: (score, outcome) pairs.

### Calibration gap

No mechanism currently maps raw scores to probabilities. This means:
- the operator cannot set a meaningful threshold like "suggest only links with >70% approval probability";
- scores from different source pages are not comparable;
- the review UI cannot display a confidence percentage.

## Source Summary

### Patent: US9189752B1 -- Interpolating Isotonic Regression for Binary Classification (Google, 2015)

**Plain-English description of the patent:**

The patent describes fitting a monotonic step function to transform raw classification scores into calibrated probabilities, then extending the step function with interpolation for smooth continuous output. The PAV (Pool Adjacent Violators) algorithm produces the step function by merging adjacent data points that violate monotonicity. Delaunay interpolation (linear interpolation between step boundaries) ensures the output is continuous and smooth.

**Repo-safe reading:**

The patent applies to any binary classification system where the raw score needs to become a probability. This repo uses it as a post-processing layer after all ranking scores are computed, transforming the composite score into a calibrated approval probability.

**What is directly supported by the patent:**

- PAV algorithm for monotonic regression on (score, outcome) pairs;
- Delaunay interpolation between PAV step boundaries;
- application to binary outcomes (approved/rejected).

**What is adapted for this repo:**

- "classification scores" map to composite ranking scores;
- "binary labels" map to editor approval (1) or rejection (0);
- the calibrated output is used for thresholding and display, not directly for re-ranking;
- scikit-learn's `IsotonicRegression` provides 90% of the implementation.

## Plain-English Summary

Simple version first.

Right now, the ranking system produces a score like 0.82 for a link suggestion. But what does 0.82 actually mean? Is it an 82% chance the link is good? Maybe, maybe not. The score is on an arbitrary scale -- it depends on the weights, the source page, and the candidate pool.

FR-065 adds a calibration layer that transforms these arbitrary scores into genuine probabilities. After calibration, a score of 0.80 truly means "historically, 80% of suggestions with this score were approved by editors."

This is done by looking at past (score, approval) pairs. The PAV algorithm fits a monotonic step function: it groups nearby scores together and computes the approval rate for each group. The result is a simple lookup: given a score of X, the historical approval rate for similar scores is Y%.

Delaunay interpolation smooths the step function so the output changes continuously (no sudden jumps at step boundaries).

The practical value: operators can set meaningful thresholds ("only show suggestions above 70% approval probability"), and the review UI can display a confidence percentage that actually means something.

## Problem Statement

Raw composite ranking scores are not calibrated probabilities. This causes three problems:

1. **Meaningless thresholds**: the operator cannot set a threshold like "only suggest links above 70% confidence" because 0.70 does not correspond to any real probability.
2. **Cross-page incomparability**: a score of 0.80 on page A may represent a stronger suggestion than 0.90 on page B, depending on the candidate distribution. There is no way to compare them.
3. **No confidence display**: the review UI cannot show "85% likely to be approved" because the raw score is not a probability.

FR-065 solves all three by fitting a calibration function that maps raw scores to genuine approval probabilities based on historical data.

## Goals

FR-065 should:

- collect (composite_score, approval_outcome) training pairs from historical suggestions;
- fit isotonic regression (PAV) on these pairs to produce a monotonic calibration function;
- extend the step function with Delaunay (linear) interpolation for continuity;
- transform each suggestion's composite score into a calibrated probability in [0, 1];
- apply calibration after all other scoring and reranking stages (it is a post-processing layer);
- retrain the calibration model periodically (default: weekly) via Celery task;
- store the calibrated probability for display and thresholding;
- keep calibration off by default until sufficient training data is available;
- fit the current Django + Celery + PostgreSQL + scikit-learn architecture.

## Non-Goals

FR-065 does not:

- change the ranking order -- calibration is a monotonic transformation, so it preserves the existing ordering;
- replace any signal computation or weight tuning mechanism;
- produce a new ranking signal (it transforms the existing composite score);
- require GPU or significant compute resources;
- handle multi-class calibration (binary only: approved vs. rejected);
- implement production code in the spec pass.

## Math-Fidelity Note

### Training data

```text
Training pairs: {(s_i, y_i)} where
  s_i = Suggestion.score_final (composite score)
  y_i in {0, 1} (0 = rejected, 1 = approved)

Sorted by score: s_1 <= s_2 <= ... <= s_n
```

### Pool Adjacent Violators (PAV) algorithm

```text
Initialise blocks: B_i = {(s_i, y_i)} with mean = y_i

While adjacent blocks violate monotonicity (mean(B_k) > mean(B_{k+1})):
  Merge B_k and B_{k+1} into one block
  Recompute block mean = sum(y in merged block) / count(merged block)

Result: step function f*(s) -> mean of block containing s
```

PAV guarantees monotonicity: higher raw scores always produce equal or higher calibrated probabilities. This is essential -- we do not want calibration to reverse the ranking.

### Delaunay interpolation (linear smoothing)

Between step boundaries, linearly interpolate:

```text
f_interp(s) = f*(s_left) + (s - s_left) / (s_right - s_left) * (f*(s_right) - f*(s_left))
```

where `s_left` and `s_right` are the nearest step boundaries below and above `s`.

For scores below the minimum training score: `f_interp(s) = f*(s_min)`.
For scores above the maximum training score: `f_interp(s) = f*(s_max)`.

### Calibrated output

```text
p_calibrated = isotonic_model.predict([composite_score])[0]
```

This is `O(log n)` via binary search on the sorted breakpoints.

### Calibration quality metric (Brier score)

```text
Brier = (1/n) * SUM_i (p_calibrated_i - y_i)^2
```

A perfectly calibrated model achieves a Brier score equal to the base rate variance. The lower the Brier score, the better the calibration.

### Reliability diagram

For operator review, bin calibrated probabilities into 10 deciles and compare:

```text
For each bin b = [0.0-0.1), [0.1-0.2), ..., [0.9-1.0]:
  predicted_mean = mean(p_calibrated in bin b)
  actual_mean = mean(y in bin b)

Perfect calibration: predicted_mean = actual_mean for all bins
```

## Scope Boundary Versus Existing Signals

FR-065 must stay separate from:

- `Wilson score intervals (FR-023)`
  - Wilson computes binomial confidence intervals on click/approval rates;
  - FR-065 transforms arbitrary composite scores into calibrated probabilities;
  - different inputs (count data vs. continuous scores), different outputs (confidence intervals vs. point probabilities).

- `Bayesian smoothing (FR-017)`
  - Bayesian smoothing regularises click rates with Beta priors;
  - FR-065 calibrates composite ranking scores, not click rates;
  - different mathematical framework and purpose.

- `All ranking signals`
  - FR-065 operates AFTER all signals are combined into the composite score;
  - it does not modify any individual signal;
  - it is a pure post-processing transformation.

Hard rule: FR-065 must not modify any signal value, any weight, or the ranking order. It is a monotonic transformation applied to the final composite score for display and thresholding purposes.

## Inputs Required

FR-065 uses only data already available:

- `Suggestion.score_final` -- composite ranking scores
- `Suggestion.status` -- editor approval labels (approved = 1, rejected = 0)
- Pairs must be from suggestions that have been reviewed (pending suggestions are excluded)

Explicitly disallowed inputs:

- individual signal scores (calibration operates on the composite only)
- analytics data (calibration is based on editor judgments)
- any data not already on the Suggestion model

## Settings And Feature-Flag Plan

### Operator-facing settings

Persist through `AppSetting`.

Recommended keys:

- `isotonic_calibration.enabled`
- `isotonic_calibration.min_training_pairs`
- `isotonic_calibration.retrain_interval_days`
- `isotonic_calibration.suggestion_threshold`

Defaults:

- `enabled = true`
- `min_training_pairs = 200`
- `retrain_interval_days = 7`
- `suggestion_threshold = 0.0` (no threshold by default -- show all suggestions)

Bounds:

- `50 <= min_training_pairs <= 5000`
- `1 <= retrain_interval_days <= 30`
- `0.0 <= suggestion_threshold <= 0.95`

### Feature-flag behavior

- `enabled = false`
  - skip calibration entirely
  - store `calibrated_probability = null`
  - store `calibration_state = disabled`
- `enabled = true` and insufficient training data
  - store `calibrated_probability = null`
  - store `calibration_state = insufficient_data`
- `enabled = true` and model available
  - compute and store calibrated probability
  - apply suggestion_threshold if set (hide suggestions below threshold)

## Diagnostics And Explainability Plan

Add one new diagnostics object per suggestion:

- `Suggestion.calibration_diagnostics`

Required per-suggestion fields:

- `calibrated_probability` -- the calibrated approval probability in [0, 1]
- `calibration_state`
  - `computed`
  - `disabled`
  - `insufficient_data`
  - `model_not_found`
  - `processing_error`
- `raw_composite_score` -- the input score before calibration

System-level diagnostics (stored in AppSetting):

- `brier_score` -- calibration quality metric
- `training_pairs_count` -- how many (score, outcome) pairs the model was trained on
- `reliability_diagram` -- 10-bin predicted vs. actual comparison
- `score_range` -- (min_score, max_score) seen in training data
- `breakpoint_count` -- number of PAV step boundaries
- `model_version` -- timestamp of the calibration model

Plain-English review helper text should say:

- `Calibrated probability means the historical approval rate for suggestions with similar scores.`
- `80% means that 80% of past suggestions scoring this high were approved by editors.`
- `This is based on historical patterns and may change as more reviews are completed.`

## Storage / Model / API Impact

### Suggestion model

Add:

- `calibrated_probability: FloatField(null=True, blank=True)`
- `calibration_diagnostics: JSONField(default=dict, blank=True)`

### Model file storage

- Calibration model serialised to `backend/ml_models/isotonic_calibration.pkl`
- File size: < 1 MB (just a list of breakpoints and values)
- Previous model kept as `isotonic_calibration_previous.pkl` for rollback

### PipelineRun snapshot

Add FR-065 settings and calibration model version to `PipelineRun.config_snapshot`.

### Backend API

Add:

- `GET /api/settings/isotonic-calibration/`
- `PUT /api/settings/isotonic-calibration/`
- `POST /api/settings/isotonic-calibration/retrain/` -- triggers manual retraining
- `GET /api/settings/isotonic-calibration/diagnostics/` -- returns system diagnostics including reliability diagram

### Review / admin / frontend

Add one new review row:

- `Approval Probability`

Add one small diagnostics block:

- calibrated probability (displayed as percentage)
- raw composite score for comparison
- neutral reason when calibration is unavailable

Add one settings card:

- enabled toggle
- minimum training pairs input
- retrain interval selector
- suggestion threshold slider (with explanation)
- reliability diagram chart (predicted vs. actual)
- Brier score display
- manual retrain button

## Backend Service Touch Points

Implementation files for the later code pass:

- `backend/apps/pipeline/services/isotonic_calibration.py` -- new service file
- `backend/apps/pipeline/services/ranker.py` -- call calibration after composite scoring
- `backend/apps/pipeline/tasks.py` -- add periodic retraining task
- `backend/apps/suggestions/models.py` -- add two new fields
- `backend/apps/suggestions/serializers.py` -- expose new fields
- `backend/apps/suggestions/views.py` -- snapshot FR-065 settings
- `backend/apps/suggestions/admin.py` -- expose new fields
- `backend/apps/suggestions/migrations/<new migration>`
- `backend/apps/core/views.py` -- add settings and diagnostics endpoints
- `backend/apps/api/urls.py` -- wire new endpoints
- `backend/apps/pipeline/tests.py` -- FR-065 unit tests
- `frontend/src/app/review/suggestion-detail-dialog.component.ts`
- `frontend/src/app/review/suggestion-detail-dialog.component.html`
- `frontend/src/app/settings/silo-settings.service.ts`
- `frontend/src/app/settings/settings.component.ts`
- `frontend/src/app/settings/settings.component.html`

Modules that must stay untouched:

- All individual signal computation files
- All weight tuning and optimisation files (FR-018, FR-060, FR-061)
- `backend/apps/content/models.py`
- `backend/apps/graph/models.py`

## Test Plan

### 1. PAV algorithm correctness

- monotonically increasing training data -> calibration function is monotonic
- non-monotonic training data -> PAV merges violating blocks correctly
- calibrated output is always in [0, 1]

### 2. Interpolation

- scores between PAV breakpoints get linearly interpolated values
- scores below minimum training score get the minimum calibrated value
- scores above maximum training score get the maximum calibrated value

### 3. Calibration quality

- on synthetic data where score = probability, Brier score is near zero
- on real data, Brier score is lower than the Brier score of uncalibrated scores

### 4. Monotonicity preservation

- ranking order before and after calibration is identical
- if score_a > score_b, then calibrated_a >= calibrated_b

### 5. Neutral fallback cases

- feature disabled -> `calibrated_probability = null`, state `disabled`
- insufficient training pairs -> `calibrated_probability = null`, state `insufficient_data`
- model file missing -> `calibrated_probability = null`, state `model_not_found`

### 6. Threshold application

- `suggestion_threshold = 0.7` -> suggestions with calibrated_probability < 0.7 are flagged
- `suggestion_threshold = 0.0` -> no suggestions are filtered

### 7. Isolation

- calibration does not modify `score_final` or any `score_*` field
- calibration does not change the ranking order

### 8. Reliability diagram

- 10-bin diagram is computed and stored in system diagnostics
- bins with sufficient data show predicted vs. actual approval rates

## Rollout Plan

### Step 1 -- compute and inspect

- train the calibration model with `suggestion_threshold = 0.0`
- inspect the reliability diagram for calibration quality
- verify Brier score is reasonable

### Step 2 -- operator review

- display calibrated probabilities in the review UI
- let the operator judge whether the percentages feel accurate
- compare calibrated probabilities against their own approval patterns

### Step 3 -- optional threshold activation

- only after calibration quality is confirmed
- start with a low threshold (e.g., 0.3) and increase gradually
- monitor whether filtered suggestions would have been rejected anyway

## Risk List

- insufficient training data produces a poor calibration function -- mitigated by `min_training_pairs` threshold of 200;
- calibration may be dataset-specific (trained on historical data, applied to new data) -- mitigated by weekly retraining to incorporate recent patterns;
- score distribution may shift when new signals or weights are added, invalidating the calibration -- mitigated by retraining after any weight change;
- operators may over-rely on calibrated probabilities as ground truth -- helper text clarifies these are historical patterns, not guarantees.

## Recommended Preset Integration

### `recommended_weights.py` entries

```python
"isotonic_calibration.enabled": "true",
"isotonic_calibration.min_training_pairs": "200",
"isotonic_calibration.retrain_interval_days": "7",
"isotonic_calibration.suggestion_threshold": "0.0",
```

**Why these values:**

- `enabled = true` -- compute calibrated probabilities from day one for display in the review UI.
- `min_training_pairs = 200` -- ensures enough data points for a meaningful calibration curve. Below 200, the step function may have too few breakpoints to be useful.
- `retrain_interval_days = 7` -- weekly retraining keeps calibration current as scoring patterns evolve.
- `suggestion_threshold = 0.0` -- no automatic filtering until the operator has validated calibration quality.

### Migration note

FR-065 must ship a new data migration that upserts these four keys into the existing `WeightPreset` record where `is_system=True` and `name='Recommended'`.
