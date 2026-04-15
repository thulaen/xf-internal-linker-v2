# FR-169 — Regression-EM Unbiased Learning-to-Rank

## Overview
Wang et al. (2018) showed that examination propensity in PBM/UBM-style click models can be treated as a regression target on session features (rank, query length, hour of day, device type), then EM-fitted alongside relevance. This produces an unbiased relevance estimate even with very sparse per-(q,d) data — the propensity model generalises across the long tail. Complements `fr165-position-bias-model` because PBM has only one parameter per rank while regression-EM lets propensity depend on arbitrary session features.

## Academic source
Full citation: **Wang, X., Bai, Y., Najork, M. & Metzler, D. (2018).** "Position Bias Estimation for Unbiased Learning to Rank in Personal Search." *Proceedings of the 2018 World Wide Web Conference (WWW)*, pp. 1685-1694. DOI: `10.1145/3178876.3186021`. (Earlier full-paper version: WSDM 2018, DOI: `10.1145/3159652.3159732`.)

## Formula
Wang et al. (2018), Equations 5-9 (the regression-EM iteration):

```
P(C = 1 | x, i) = θ_i(x; ψ) · γ(q, d; φ)

E-step:
  Estimate posterior P(R = 1 | C, x, i) using current (ψ, φ)

M-step (regression-EM):
  ψ ← argmax_ψ  Σ_{rows}  log θ_i(x; ψ) · 1[examined]
              (logistic regression on session features x)
  φ ← argmax_φ  Σ_{rows}  log γ(q, d; φ) · 1[relevant]
              (logistic regression on (q, d) features)

where
  x          = session feature vector (rank, hour, device, query-length, ...)
  ψ          = parameters of the propensity regression
  φ          = parameters of the relevance regression
```

Wang et al. report 5-15% NDCG@5 improvement over PBM on Gmail search logs.

## Starting weight preset
```python
"reg_em.enabled": "true",
"reg_em.ranking_weight": "0.0",
"reg_em.em_max_iters": "10",
"reg_em.feature_set": "rank,hour,device,query_len",
"reg_em.l2_reg": "0.01",
```

## C++ implementation
- File: `backend/extensions/regression_em.cpp`
- Entry: `RegEMParams reg_em_fit(const ImpressionLog& log, const FeatureSpec& spec, int max_iters)`
- Complexity: O(I · L · F) where I = EM iters, L = impressions, F = features per row; logistic-regression M-step uses L-BFGS
- Thread-safety: per-thread M-step accumulators; gradients reduced after each iter
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/regression_em.py::reg_em_fit` using sklearn `LogisticRegression` for each M-step.

## Benchmark plan

| Size | Impressions | C++ target | Python target |
|---|---|---|---|
| Small | 1k rows | 8 ms | 400 ms |
| Medium | 100k rows | 700 ms | 50 s |
| Large | 10M rows | 70 s | 1 hr |

## Diagnostics
- Propensity coefficients ψ (per feature) on Performance dashboard
- Per-(q,d) γ logit shown in suggestion detail
- C++/Python badge
- Fallback flag
- Debug fields: `em_iters_used`, `final_loglik`, `feature_importances`

## Edge cases & neutral fallback
- (q,d) with no impressions → relevance falls back to PBM γ
- EM non-convergence after `max_iters` → emit warning, use last estimate
- Highly correlated features → L2 regularisation prevents collinearity blow-up
- Numerical stability: log-space gradient accumulation

## Minimum-data threshold
At least 100 impressions per query family (not per (q,d)) for regression to generalise.

## Budget
Disk: 2 MB (model coefficients) + 5 MB γ table  ·  RAM: 800 MB during EM for largest log tier

## Scope boundary vs existing signals
Distinct from `fr162-cascade-click-model`, `fr163-dbn-click-model`, `fr164-user-browsing-model`, `fr165-position-bias-model` — all of those have either no propensity model or a single per-rank table. Regression-EM is the only signal that learns propensity as a function of arbitrary session features, generalising across the long tail.

## Test plan bullets
- Unit: synthetic log with rank as only signal → recovers PBM equivalent
- Unit: device-conditional propensity → ψ assigns nonzero coefficient to device
- Parity: C++ vs Python EM within 1e-3 NDCG@5 on 100k rows
- Edge: zero-impression (q,d) falls back to PBM
- Edge: feature with zero variance dropped from regression (defensive)
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
