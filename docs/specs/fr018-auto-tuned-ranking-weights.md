# FR-018 - Auto-Tuned Ranking Weights & Safe Dated Model Promotion

## Goal
To automatically refine ranking weights using a feedback loop from GA4 engagement data, Matomo unsampled click data, GSC search performance, and human reviewer decisions.

## Source of Truth
- **Patent Inspiration**: **US8661029B1** (Google) - "Modifying search result ranking based on implicit user feedback."
- **Math**: **Bayesian Optimization** or **Gradient Descent** on a "Lift" metric derived from GSC clicks, GA4 engagement, and Matomo unsampled per-suggestion clicks.

## How it works (The Python Tuning Loop)

Auto-weight tuning is implemented in Python at `backend/apps/suggestions/services/weight_tuner.py` and orchestrated by Celery tasks in `backend/apps/pipeline/tasks.py` (Part 8). The legacy C# HttpWorker analytics service was decommissioned in 2026-04 and the R analytics service was retired before that — this spec describes the live Python implementation.

### 1. Data Collection (PostgreSQL → Python WeightTuner)
- `WeightTuner.run()` queries PostgreSQL via the Django ORM:
    - `Suggestion` approval/rejection rates and per-signal scores (`score_semantic`, `score_keyword`, `score_node_affinity`, `score_quality`) from `suggestions_suggestion`, filtered by `status__in=["approved", "rejected"]` and `reviewed_at__gte=cutoff` (default 90-day lookback).
    - The downstream `evaluate_weight_challenger` task uses `SearchMetric`, `GSCDailyPerformance`, and the GA4 / Matomo telemetry surfaces (FR-016) to validate post-promotion impact.
    - **Matomo** unsampled per-suggestion click counts from `analytics_suggestiontelemetrydaily WHERE telemetry_source = 'matomo'` (FR-016). Matomo is preferred for per-suggestion click accuracy because GA4 buckets low-volume suggestions into `(other)` at scale. When Matomo data is available for a suggestion, it takes precedence over the GA4 click count for that signal.
- Skip threshold: < 50 reviewed samples in the lookback window means the run logs `"Insufficient samples for tuning"` and exits without creating a challenger.

### 2. Weight Tuning (Python + scipy.optimize)
- **Objective Function (`WeightTuner.run().objective`)**: bounded binary cross-entropy on the four blend weights, with a quadratic drift penalty:
  - `loss = BCE(y, sigmoid(15 * (X · w_norm − 0.7))) + 0.1 * Σ(w − w_init)²`
  - `y` is the per-sample approve / reject label, `X` is the four-column feature matrix (`score_semantic`, `score_keyword`, `score_node_affinity`, `score_quality`), `w_norm` is `w / Σw` (so the optimizer never has to enforce a sum constraint), and the `15` and `0.7` constants center the logistic around the strong-suggestion quality threshold.
- Optimization uses **`scipy.optimize.minimize(method="L-BFGS-B")`** with per-weight bounds `[max(0, w_init - 0.05), min(1, w_init + 0.05)]`. `w_init` is normalized before bounds, remainder math, and objective evaluation. The final candidate is projected back into that bounded simplex, so persisted candidate weights sum to `1.0` and no weight moves more than `0.05` from the normalized baseline.
- After optimization, the same objective is evaluated at both `w_init` and `w_opt` to produce `champion_quality_score = 1 / (1 + champion_loss)` and `predicted_quality_score = 1 / (1 + candidate_loss)` — both bounded in `(0, 1]`, both used by the SPRT comparator in `evaluate_weight_challenger`.
- Produces a "Candidate Weight Set."

### 3. Challenger Creation (Python WeightTuner → Django ORM)
- `WeightTuner.run()` writes a `RankingChallenger` row with `status='pending'`, `candidate_weights`, `baseline_weights`, `predicted_quality_score`, and `champion_quality_score`.
- The optimizer only tunes the four blend weights (`w_semantic`, `w_keyword`, `w_node`, `w_quality`); the remaining ranker weights are passed through unchanged when `evaluate_weight_challenger` later calls `apply_weights`.

### 4. Verification (Champion vs Challenger)
- The system runs the "Champion" (Active) and "Challenger" (New) side-by-side.
- If the Challenger shows a >5% improvement in predicted link quality without breaking hard constraints, it is promoted.

## Safe Dated Promotion
- Every change is logged with a timestamped record.
- **Rollback**: If the new weights cause a sudden drop in GSC clicks, the system rolls back to the previous known-good version automatically.

## Slices for Execution

### Slice 1: Django — Challenger model & internal write endpoint
- `RankingChallenger` model: stores `candidate_weights`, `baseline_weights`, `status` (`pending` / `promoted` / `rolled_back` / `rejected`), `predicted_quality_score`, `champion_quality_score`, and a run reference.
- Internal-only POST endpoint `/api/internal/weight-challenger/` for manual challenger submissions.
- Migration `0020_fr018_ranking_challenger`.

### Slice 2: Python — Data collection & L-BFGS-B optimizer
- `backend/apps/suggestions/services/weight_tuner.py` (`WeightTuner` class).
- ORM queries for the four blend signals (`score_semantic`, `score_keyword`, `score_node_affinity`, `score_quality`) plus approve/reject labels.
- Bounded binary-cross-entropy objective with `0.1 * sum((w - w_init)^2)` drift regularizer; `scipy.optimize.minimize(method="L-BFGS-B")` with `+/-0.05` per-weight bounds around the normalized baseline and post-optimization bounded-simplex projection.
- Computes both `champion_quality_score` and `predicted_quality_score` using `quality = 1 / (1 + loss)` for use by the SPRT comparator in Slice 4.
- Unit tests with synthetic data in `backend/apps/suggestions/tests.py`.

### Slice 3: Celery — Run trigger
- Beat schedule entry `monthly-python-weight-tune` (first Sunday, 13:45 UTC) → `pipeline.monthly_weight_tune` Celery task in `backend/apps/pipeline/tasks.py`.
- Manual trigger via `POST /api/settings/weight-tune/trigger/` (see `backend/apps/core/views.py`).
- The task instantiates `WeightTuner(lookback_days=90).run(run_id)` and chains `evaluate_weight_challenger.delay(run_id=run_id)` on success.

### Slice 4: Django — Champion vs Challenger evaluation, promotion & rollback
- Celery task `evaluate_weight_challenger`: reads `predicted_quality_score` and `champion_quality_score` from the pending RankingChallenger and runs `ChallengerSPRTEvaluator(min_improvement_ratio=1.05)` against them.
- Auto-promotes if SPRT decides "promote" — applies the four weights via `apply_weights(...)` and creates a `WeightAdjustmentHistory` row with `source='auto_tune'`.
- Rollback task `check_weight_rollback` (weekly): if GSC clicks drop > 15 % within the 14-day window after promotion, revert to `baseline_weights`, mark challenger `rolled_back`, and write a second `WeightAdjustmentHistory` row with `source='auto_tune'`.

### Slice 5: Angular — Weight Tuning card in Settings
- Shows current champion weights (read from `AppSetting`).
- If a pending challenger exists, shows a diff of what would change.
- Manual "Promote" and "Reject" buttons for human override.
- History table of past auto-tune events (from `WeightAdjustmentHistory`).

## Gate Justifications (RANKING-GATES Gate A)

This spec was originally written when the auto-tuner was implemented in C# (`HttpWorker.Analytics`). The 2026-04-26 rewrite of sections "How it works" and Slices 1–4 reflects the live Python port at `backend/apps/suggestions/services/weight_tuner.py` + the Celery task chain in `backend/apps/pipeline/tasks.py`. The objective function, search space, drift bounds, SPRT comparator threshold, and Recommended preset defaults are unchanged — only the implementation language and the helper file paths moved. No new ranking signal, hyperparameter, or weight-preset key was added in the 2026-04-26 cleanup, so Gate A's A1–A12 status carries over from the original FR-018 spec without re-derivation.
