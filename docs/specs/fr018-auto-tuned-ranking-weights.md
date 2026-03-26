# FR-018 - Auto-Tuned Ranking Weights & Safe Dated Model Promotion

## Goal
To automatically refine ranking weights using a feedback loop from GA4 engagement data, GSC search performance, and human reviewer decisions.

## Source of Truth
- **Patent Inspiration**: **US8661029B1** (Google) - "Modifying search result ranking based on implicit user feedback."
- **Math**: **Bayesian Optimization** or **Gradient Descent** on a "Lift" metric derived from GSC clicks and GA4 engagement.

## How it works (The R Loop)

### 1. Data Collection (Django -> R)
- R service pulls the following via the Django API:
    - `Suggestion` approval/rejection rates.
    - `LinkFreshness` and `ExistingLink` topology.
    - `GSC` baseline vs. post-apply impressions/clicks.
    - `GA4` dwell time and click-through rates.

### 2. Weight Tuning (R)
- **Objective Function**: $Maximize(Impact) = w_1(GSC_{lift}) + w_2(GA4_{dwell}) + w_3(Review_{approval})$.
- R uses a **Search Algorithm** to find the optimal set of weights that would have predicted the most successful links in history.
- It produces a "Candidate Weight Set."

### 3. Challenger Creation (R -> Django)
- R sends the candidate weights back to Django.
- Django saves them as a **Challenger** model, e.g., `april_18_2026_pagerank_score`.

### 4. Verification (Champion vs Challenger)
- The system runs the "Champion" (Active) and "Challenger" (New) side-by-side.
- If the Challenger shows a >5% improvement in predicted link quality without breaking hard constraints, it is promoted.

## Safe Dated Promotion
- Every change is logged with a timestamped record.
- **Rollback**: If the new weights cause a sudden drop in GSC clicks, the system rolls back to the previous known-good version automatically.
