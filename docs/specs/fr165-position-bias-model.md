# FR-165 — Position-Bias Model (PBM)

## Overview
PBM is the simplest unbiased click model: it assumes the click probability factorises into a per-rank examination prior `θ_i` and a per-(q,d) relevance `γ_{q,d}`. It is the reference baseline against which CCM, DBN, and UBM are measured. Provides a clean attractiveness estimate that is cheap to compute. Complements `fr162-cascade-click-model` because PBM has no inter-position dependency.

## Academic source
Full citation: **Richardson, M., Dominowska, E. & Ragno, R. (2007).** "Predicting Clicks: Estimating the Click-Through Rate for New Ads." *Proceedings of the 16th International Conference on World Wide Web (WWW)*, pp. 521-530. DOI: `10.1145/1242572.1242643`.

## Formula
Richardson, Dominowska & Ragno (2007), Equation 4 (the position-bias factorisation):

```
P(C = 1 | q, d, i) = θ_i · γ_{q, d}

where
  θ_i      = examination probability at rank i (rank-only prior)
  γ_{q,d}  = perceived relevance of (q, d), independent of rank
```

θ_i is estimated by EM with normalisation θ_1 = 1; γ then has scale [0, 1].

## Starting weight preset
```python
"pbm.enabled": "true",
"pbm.ranking_weight": "0.0",
"pbm.max_rank": "10",
"pbm.em_max_iters": "15",
```

## C++ implementation
- File: `backend/extensions/pbm.cpp`
- Entry: `PBMParams pbm_em(const ImpressionLog& log, int max_rank, int max_iters)`
- Complexity: O(I · L) per EM iter — fastest of all click models in this block
- Thread-safety: per-thread accumulators reduced after each iter
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/click_models.py::pbm_em` using numpy and sklearn-style EM loop.

## Benchmark plan

| Size | Impressions | C++ target | Python target |
|---|---|---|---|
| Small | 1k rows | 2 ms | 80 ms |
| Medium | 100k rows | 200 ms | 12 s |
| Large | 10M rows | 20 s | 12 min |

## Diagnostics
- θ curve (rank vs examination prob) on Performance dashboard
- Per-(q,d) γ value in suggestion detail
- C++/Python badge
- Fallback flag
- Debug fields: `em_iters_used`, `theta_curve`, `final_loglik`

## Edge cases & neutral fallback
- (q,d) with no impressions → γ neutral 0.5
- All-zero clicks → γ pinned to small prior
- Rank > `max_rank` clipped to `max_rank`
- θ_1 fixed at 1.0 to break scale ambiguity

## Minimum-data threshold
At least 20 impressions per (q,d) before γ is published.

## Budget
Disk: 4 MB γ table + 80 B θ vector  ·  RAM: 100 MB during EM

## Scope boundary vs existing signals
Foundational: PBM is the simplest of the click-model family (FR-162 to FR-167). DCM, CCM-Bayes, UBM, and DBN all extend the same factorisation with extra latent state — PBM is the no-state baseline.

## Test plan bullets
- Unit: synthetic log where rank-1 always clicks → θ_1 = 1.0, γ ≈ 1.0
- Unit: rank-2 clicks at half rate → θ_2 ≈ 0.5
- Parity: C++ vs Python EM within 1e-4 on 10k rows
- Edge: empty log returns priors only
- Edge: ranks > max_rank clipped, no out-of-bounds
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
