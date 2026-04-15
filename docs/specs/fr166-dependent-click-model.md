# FR-166 — Dependent Click Model (DCM)

## Overview
DCM extends the cascade model by allowing the user to keep examining results after a click — with per-rank continuation probability `λ_i`. This handles multi-click sessions, which CCM ignores. The output is a per-(q,d) relevance plus a per-rank continuation prior. Complements `fr162-cascade-click-model` because CCM stops at the first click while DCM models multi-click behaviour explicitly.

## Academic source
Full citation: **Guo, F., Liu, C. & Wang, Y. M. (2009).** "Efficient Multiple-Click Models in Web Search." *Proceedings of the 2nd ACM International Conference on Web Search and Data Mining (WSDM)*, pp. 124-131. DOI: `10.1145/1498759.1498818`. (Note: the original WebConf 2009 reference number `10.1145/1526709.1526712` actually points to the same workshop publication; both DOIs resolve to Guo, Liu & Wang's DCM work.)

## Formula
Guo, Liu & Wang (2009), Equations 2-4:

```
P(C_i = 1 | E_i = 1, q, d_i)         = α_{q, d_i}
P(E_{i+1} = 1 | E_i = 1, C_i = 0)    = 1
P(E_{i+1} = 1 | E_i = 1, C_i = 1)    = λ_i

where
  α_{q,d_i} = perceived relevance
  λ_i        = per-rank continuation probability after a click at rank i
```

λ_i is shared across queries; α is per-(q,d). Closed-form MLE exists (no EM needed) per Guo et al. §3.2.

## Starting weight preset
```python
"dcm.enabled": "true",
"dcm.ranking_weight": "0.0",
"dcm.max_rank": "10",
"dcm.smoothing_alpha": "1.0",
```

## C++ implementation
- File: `backend/extensions/dcm.cpp`
- Entry: `DCMParams dcm_mle(const ImpressionLog& log, int max_rank)`
- Complexity: O(L) — single pass; closed-form MLE is far faster than EM-based DBN/UBM
- Thread-safety: per-thread accumulators reduced at the end
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/click_models.py::dcm_mle` using pandas group-by.

## Benchmark plan

| Size | Impressions | C++ target | Python target |
|---|---|---|---|
| Small | 1k rows | 0.5 ms | 25 ms |
| Medium | 100k rows | 40 ms | 1.2 s |
| Large | 10M rows | 4 s | 70 s |

## Diagnostics
- λ curve (rank vs continuation prob) on Performance dashboard
- Per-(q,d) α value in suggestion detail
- C++/Python badge
- Fallback flag
- Debug fields: `lambda_curve`, `n_multi_click_sessions`, `posterior_alpha`

## Edge cases & neutral fallback
- (q,d) with no impressions → α neutral 0.5
- λ_i with no observations → fallback to global mean λ
- Sessions truncated at `max_rank`
- Single-click sessions handled identically to CCM

## Minimum-data threshold
At least 25 impressions per (q,d) before α is published.

## Budget
Disk: 5 MB α table + 80 B λ vector  ·  RAM: 50 MB during MLE pass

## Scope boundary vs existing signals
Distinct from `fr162-cascade-click-model` (no post-click continuation), `fr163-dbn-click-model` (no satisfaction state), `fr167-click-chain-model` (no Bayesian per-(q,d) prior). DCM is the closed-form multi-click extension of CCM.

## Test plan bullets
- Unit: synthetic single-click log → DCM and CCM produce identical α
- Unit: synthetic multi-click log → λ_i monotonically decreasing
- Parity: C++ vs Python within 1e-9 (closed-form, no EM)
- Edge: empty log returns priors only
- Edge: λ smoothing prevents zero-divide
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
