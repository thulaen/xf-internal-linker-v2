# FR-167 — Click Chain Model (CCM-Bayes)

## Overview
The Click Chain Model places Bayesian Beta priors over per-(q,d) relevance and updates them by walking the click chain top-to-bottom. Unlike DBN, it has closed-form posterior updates per query session — no EM required. The output is a posterior mean and variance for each (q,d), which feeds both the ranker and the explore-exploit (Thompson) sampler. Complements `fr163-dbn-click-model` because DBN gives MLE point estimates while CCM-Bayes gives full posterior distributions.

## Academic source
Full citation: **Guo, F., Liu, C., Kannan, A., Minka, T., Taylor, M., Wang, Y. M. & Faloutsos, C. (2009).** "Click Chain Model in Web Search." *Proceedings of the 18th International Conference on World Wide Web (WWW)*, pp. 11-20. DOI: `10.1145/1526709.1526712`. (Stable application reference: SIGIR 2009 follow-up DOI: `10.1145/1571941.1572007`.)

## Formula
Guo et al. (2009), Equations 3-7:

```
P(C_i = 1 | E_i = 1, q, d_i) = R_{q, d_i}                      (relevance)
P(E_{i+1} = 1 | E_i, C_i)    = α_1 (1−C_i) + α_2 C_i (1−R) + α_3 C_i R

R_{q, d_i} ~ Beta(a_{q,d_i}, b_{q,d_i})

Posterior update after seeing (E_i, C_i):
  if C_i = 1:  a += 1
  if E_i = 1, C_i = 0:  b += 1
```

α_1, α_2, α_3 are global continuation hyperparameters (Guo et al. report 0.5 / 0.7 / 0.3 on Bing logs).

## Starting weight preset
```python
"ccm_bayes.enabled": "true",
"ccm_bayes.ranking_weight": "0.0",
"ccm_bayes.alpha_1": "0.5",
"ccm_bayes.alpha_2": "0.7",
"ccm_bayes.alpha_3": "0.3",
"ccm_bayes.prior_a": "1.0",
"ccm_bayes.prior_b": "1.0",
```

## C++ implementation
- File: `backend/extensions/click_chain.cpp`
- Entry: `CCMPosterior ccm_bayes_update(const ImpressionLog& log, CCMHyperparams hp)`
- Complexity: O(L) — closed-form posterior update per impression row
- Thread-safety: per-thread (a, b) accumulators reduced at end
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/click_models.py::ccm_bayes_update` using numpy with vectorised Beta updates.

## Benchmark plan

| Size | Impressions | C++ target | Python target |
|---|---|---|---|
| Small | 1k rows | 0.6 ms | 30 ms |
| Medium | 100k rows | 50 ms | 1.5 s |
| Large | 10M rows | 5 s | 90 s |

## Diagnostics
- Per-(q,d) Beta(a, b) shown in suggestion detail with mean ± 1σ
- C++/Python badge
- Fallback flag
- Debug fields: `posterior_a`, `posterior_b`, `posterior_variance`

## Edge cases & neutral fallback
- (q,d) with no observations → posterior = prior Beta(1,1), mean 0.5
- α_2 + α_3 must be ≤ 1 (validated at config load)
- Numerical stability: a and b stored as float64
- Sessions truncated at 10 ranks

## Minimum-data threshold
None — Bayesian model is defined for any sample size; posterior variance encodes uncertainty.

## Budget
Disk: 6 MB ((a, b) per (q,d))  ·  RAM: 60 MB during pass

## Scope boundary vs existing signals
Distinct from `fr162-cascade-click-model` (point MLE only), `fr163-dbn-click-model` (no posterior variance), `fr013-feedback-driven-explore-exploit-reranking` (Thompson sampling at presentation time, not posterior estimation). CCM-Bayes is the only signal that produces full posterior distributions.

## Test plan bullets
- Unit: zero observations → posterior equals prior
- Unit: 100 clicks, 0 skips → posterior mean ≈ 1.0 with low variance
- Parity: C++ vs Python within 1e-9 (closed-form, no EM)
- Edge: invalid hyperparameters (α_2 + α_3 > 1) rejected at config load
- Edge: posterior variance non-negative at all sample sizes
- Integration: feeds Thompson sampler when both enabled
- Regression: ranking unchanged when weight = 0.0
