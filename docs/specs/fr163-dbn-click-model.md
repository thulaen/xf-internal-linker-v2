# FR-163 — Dynamic Bayesian Network (DBN) Click Model

## Overview
The DBN click model decomposes user behaviour into perceived relevance `α` (attractiveness, drives click) and actual relevance `σ` (satisfaction, drives stop) plus a continuation prior `γ`. After a click, the user continues only with probability `γ(1 − σ)`. Inverting this gives both an attractiveness and a satisfaction signal per (q,d) — the satisfaction term is the strongest single click-derived ranker prior in the literature. Complements `fr162-cascade-click-model` because CCM has only one parameter per (q,d) while DBN separates examination, attractiveness, and satisfaction.

## Academic source
Full citation: **Chapelle, O. & Zhang, Y. (2009).** "A Dynamic Bayesian Network Click Model for Web Search Ranking." *Proceedings of the 18th International Conference on World Wide Web (WWW)*, pp. 1-10. DOI: `10.1145/1526709.1526711`.

## Formula
Chapelle & Zhang (2009), §3 (equations 1-7):

```
P(C_i = 1 | E_i = 1)         = α_{q, d_i}                  (attractiveness)
P(S_i = 1 | C_i = 1)         = σ_{q, d_i}                  (satisfaction)
P(E_{i+1} = 1 | E_i = 1, S_i = 0) = γ                       (continuation prior)
P(E_{i+1} = 1 | S_i = 1)         = 0
P(E_1 = 1)                       = 1

C_i = E_i · A_i  with A_i ~ Bernoulli(α)
S_i = C_i · R_i  with R_i ~ Bernoulli(σ)
```

Parameters estimated via EM. `σ` is the unbiased relevance estimate used for ranking.

## Starting weight preset
```python
"dbn.enabled": "true",
"dbn.ranking_weight": "0.0",
"dbn.continuation_gamma": "0.7",
"dbn.em_max_iters": "20",
"dbn.em_tolerance": "1e-4",
```

## C++ implementation
- File: `backend/extensions/dbn_click_model.cpp`
- Entry: `DBNParams dbn_em(const ImpressionLog& log, int max_iters, double tol)`
- Complexity: O(I · L · K) where I = EM iters, L = impressions, K = avg session length; per Chapelle & Zhang §3.2 each iteration is O(L)
- Thread-safety: per-thread E-step accumulators reduced for M-step
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/click_models.py::dbn_em` using numpy with vectorised E-step.

## Benchmark plan

| Size | Impressions | C++ target | Python target |
|---|---|---|---|
| Small | 1k rows | 5 ms | 200 ms |
| Medium | 100k rows | 400 ms | 25 s |
| Large | 10M rows | 40 s | 25 min |

## Diagnostics
- Per-(q,d) α and σ values in suggestion detail
- EM convergence curve on Performance dashboard
- C++/Python badge
- Fallback flag
- Debug fields: `em_iters_used`, `final_loglik`, `gamma_estimate`

## Edge cases & neutral fallback
- (q,d) with no clicks → σ posterior pinned to prior
- EM non-convergence after `max_iters` → emit warning, use last estimate
- Numerical underflow in long sessions → log-space accumulation
- Continuation prior γ shared across queries (per paper §3.3)

## Minimum-data threshold
At least 30 impressions per (q,d) before σ is published; otherwise fallback to CCM α.

## Budget
Disk: 8 MB (per-(q,d) α and σ tables)  ·  RAM: 200 MB during EM

## Scope boundary vs existing signals
Distinct from `fr162-cascade-click-model` (single-parameter, no satisfaction) and `fr164-user-browsing-model` (no satisfaction state). DBN is the only signal in the stack that estimates post-click satisfaction.

## Test plan bullets
- Unit: synthetic log where every clicked result is satisfying → σ ≈ 1.0
- Unit: synthetic log with high re-click rate after a doc → σ ≈ 0.0
- Parity: C++ EM vs Python EM convergence within 1e-3 on 10k rows
- Edge: zero-click log returns prior σ
- Edge: EM hits max_iters without convergence emits warning
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
