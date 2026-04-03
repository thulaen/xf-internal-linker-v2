# Spec: FR-017 Slice 4 (Bayesian Math Refinement)

This document defines the mathematical and technical requirements for the GSC Search Outcome Attribution engine in the C# `http-worker`. It aims to deliver a high-fidelity "Probability of Uplift" signal for internal link experiments.

## 1. Problem Statement
Raw GSC data is noisy. A 100% lift on a 1-click page is statistically meaningless. Conversely, a 5% drop on a growing site is actually a significant loss. We need a model that:
1.  **Regresses toward the mean** for low-traffic pages (Bayesian Smoothing).
2.  **Normalizes against market trends** (Causal Normalization).

## 2. Statistical Model: Simplified Bayesian Causal Lift

### A. Data Inputs
-   $T_{pre}$: Target page clicks in the baseline window (e.g., 28 days before apply).
-   $T_{post}$: Target page clicks in the observation window (e.g., 28 days after apply).
-   $C_{pre}$: Global site clicks (excluding target) in the baseline window.
-   $C_{post}$: Global site clicks (excluding target) in the observation window.

### B. Causal Normalization (The Counterfactual)
We predict what the target page *would have done* if no link was applied, assuming it followed the site-wide trend:
$$\hat{T}_{post} = C_{post} \times \frac{T_{pre} + \alpha}{C_{pre} + \alpha + \beta}$$
*Note: We include small \alpha, \beta smoothing here to avoid division-by-zero or extreme ratios if the baseline is zero.*

### C. Bayesian Posterior (Monte Carlo)
We model the target page's performance as a Poisson or Negative Binomial process (for counts) or a Beta process (for CTR). For simplicity and robustness across traffic scales, we use **Gamma-Poisson Conjugacy** for click counts:
1.  **Prior**: Gamma distribution $(\alpha, \beta)$ based on the predicted counterfactual $\hat{T}_{post}$.
2.  **Observed**: Poisson distribution with rate $\lambda$ from actual $T_{post}$.
3.  **Simulation**: 
    - Sample $S_{predicted}$ from the Counterfactual distribution.
    - Sample $S_{observed}$ from the Post-Apply distribution.
    - **Probability of Uplift**: $P(S_{observed} > S_{predicted})$.

### D. Reward Labeling
-   **Positive**: Prob > 95% AND Relative Lift > 5%.
-   **Negative**: Prob < 5% AND Relative Lift < -5%.
-   **Neutral**: Prob between 5-95%.
-   **Inconclusive**: Total impressions < threshold (e.g., 100 in window).

## 3. Implementation Details (C#)
-   **Library**: `MathNet.Numerics` (already confirmed in `GSCAttributionService.cs`).
-   **Service**: `GSCAttributionService`.
-   **Method**: `AnalyzeUpliftAsync`.

## 4. Integration Strategy
- **Worker Job**: Triggered via Redis `JobQueue` by the Django Celery task `sync_gsc_performance`.
- **Persistence**: Results are PUT back to the Django API and stored in `GSCImpactSnapshot`.

## 5. Anti-Duplication Note
- **DO NOT** rebuild the GSC Importer (already in Python).
- **DO NOT** rebuild the Settings UI (already in Angular).
- **FOCUS** strictly on the `AnalyzeUpliftAsync` logic and the communication bridge between Python and C#.
