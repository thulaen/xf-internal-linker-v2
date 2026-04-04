# FR-018 - Auto-Tuned Ranking Weights & Safe Dated Model Promotion

## Goal
To automatically refine ranking weights using a feedback loop from GA4 engagement data, Matomo unsampled click data, GSC search performance, and human reviewer decisions.

## Source of Truth
- **Patent Inspiration**: **US8661029B1** (Google) - "Modifying search result ranking based on implicit user feedback."
- **Math**: **Bayesian Optimization** or **Gradient Descent** on a "Lift" metric derived from GSC clicks, GA4 engagement, and Matomo unsampled per-suggestion clicks.

## How it works (The C# Tuning Loop)

The R analytics service has been removed. Auto-weight tuning is implemented in C# inside `services/http-worker/src/HttpWorker.Analytics/` using LINQ for data aggregation and MathNet.Numerics for optimization.

### 1. Data Collection (Postgres -> C# Analytics Worker)
- C# Analytics Worker queries PostgreSQL directly via Npgsql:
    - `Suggestion` approval/rejection rates from `suggestions_suggestion`.
    - `LinkFreshness` and `ExistingLink` topology from `graph_*` tables.
    - `GSC` baseline vs. post-apply impressions/clicks from `analytics_searchmetric`.
    - `GA4` dwell time and click-through rates from `analytics_suggestiontelemetrydaily WHERE telemetry_source = 'ga4'` (FR-016).
    - **Matomo** unsampled per-suggestion click counts from `analytics_suggestiontelemetrydaily WHERE telemetry_source = 'matomo'` (FR-016). Matomo is preferred for per-suggestion click accuracy because GA4 buckets low-volume suggestions into `(other)` at scale. When Matomo data is available for a suggestion, it takes precedence over the GA4 click count for that signal.

### 2. Weight Tuning (C# + MathNet.Numerics)
- **Objective Function**: `Maximize(Impact) = w1 * GSC_lift + w2 * GA4_dwell + w3 * Review_approval + w4 * Matomo_click_rate`
  - `GSC_lift` — change in organic clicks/impressions after a suggestion was applied
  - `GA4_dwell` — average engaged session time on destination pages reached via suggestion links
  - `Review_approval` — historical approval rate for suggestions with similar signal profiles
  - `Matomo_click_rate` — unsampled CTR per suggestion from Matomo (falls back to GA4 if Matomo data unavailable)
- Optimization uses **MathNet.Numerics L-BFGS** to find the weight vector that best predicts successful links in historical data.
- Each run is bounded: maximum delta of `±0.05` per weight per run. No weight may drift more than `0.20` from the documented recommended baseline without a manual review flag.
- Produces a "Candidate Weight Set."

### 3. Challenger Creation (C# -> Django via Npgsql)
- C# writes the candidate weights directly to `core_appsetting` via a whitelisted key set.
- Django reads them as a **Challenger** model, e.g., `april_18_2026_weights`.

### 4. Verification (Champion vs Challenger)
- The system runs the "Champion" (Active) and "Challenger" (New) side-by-side.
- If the Challenger shows a >5% improvement in predicted link quality without breaking hard constraints, it is promoted.

## Safe Dated Promotion
- Every change is logged with a timestamped record.
- **Rollback**: If the new weights cause a sudden drop in GSC clicks, the system rolls back to the previous known-good version automatically.

## Slices for Execution

### Slice 1: Django — Challenger model & internal write endpoint
- New `RankingChallenger` model: stores candidate weight JSON, `status` (`pending` / `promoted` / `rolled_back`), predicted quality scores, and a run reference.
- Internal-only POST endpoint `/api/internal/weight-challenger/` that C# calls to land a new candidate.
- Migration.

### Slice 2: C# — Data collection & L-BFGS optimizer
- New `HttpWorker.Analytics` namespace under `HttpWorker.Services`.
- `WeightTunerDataCollector` — Npgsql queries for all 4 signals (GSC lift, GA4 dwell, review approval rate, Matomo click rate with GA4 fallback).
- `WeightObjectiveFunction` — MathNet.Numerics L-BFGS optimizer, bounded to `±0.05` per weight per run and `0.20` max drift from baseline.
- Unit tests with synthetic data.

### Slice 3: C# — Run trigger & Django write
- `WeightTuningController` with POST `/api/v1/weight-tuning/run`.
- Orchestrates: collect → optimize → apply bounds → POST candidate to Django's internal endpoint.
- Hook into `JobsController` so Django can trigger a tune run like any other job.

### Slice 4: Django — Champion vs Challenger evaluation, promotion & rollback
- Celery task `evaluate_weight_challenger`: scores both sets of weights against recent historical data.
- Auto-promotes challenger if it beats champion by >5% predicted quality — applies weights to `AppSetting`, creates a `WeightAdjustmentHistory` row with `source='cs_auto_tune'`.
- Rollback task: if GSC clicks drop within a configurable window after promotion, revert and mark challenger `rolled_back`.

### Slice 5: Angular — Weight Tuning card in Settings
- Shows current champion weights (read from `AppSetting`).
- If a pending challenger exists, shows a diff of what would change.
- Manual "Promote" and "Reject" buttons for human override.
- History table of past auto-tune events (from `WeightAdjustmentHistory`).
