# FR-162 — Cascade Click Model (CCM)

## Overview
The Cascade Click Model assumes a user examines suggestions top-to-bottom and stops at the first click. Inverting observed clicks under this model gives an unbiased per-position relevance estimate `α_{q,d}` that the ranker can use as a behavioural prior — far more accurate than raw CTR. Complements `fr012-click-distance-structural-prior` because that signal uses page graph distance while CCM uses click-stream evidence.

## Academic source
Full citation: **Craswell, N., Zoeter, O., Taylor, M. & Ramsey, B. (2008).** "An experimental comparison of click position-bias models." *Proceedings of the 1st ACM International Conference on Web Search and Data Mining (WSDM)*, pp. 87-94. DOI: `10.1145/1341531.1341545`.

## Formula
Craswell et al. (2008), §2.2 (Cascade Model):

```
P(C_i = 1)               = P(E_i = 1) · α_{q, d_i}
P(E_1 = 1)               = 1
P(E_{i+1} = 1 | E_i, C_i) = (1 − C_i) · 1[E_i = 1]

where
  C_i      = click on rank-i suggestion
  E_i      = examined rank-i suggestion
  α_{q,d_i} = perceived relevance of (query q, document d_i)
```

The key insight: examination ends at the first click, so α can be MLE-estimated per position from impression/click logs.

## Starting weight preset
```python
"ccm.enabled": "true",
"ccm.ranking_weight": "0.0",
"ccm.min_impressions": "20",
"ccm.smoothing_alpha": "1.0",
```

## C++ implementation
- File: `backend/extensions/cascade_click_model.cpp`
- Entry: `std::vector<double> ccm_relevance(const ImpressionLog& log)` returning per-(q,d) α
- Complexity: O(L) where L = total impression rows; one pass to accumulate examine and click counts
- Thread-safety: per-thread accumulators reduced at the end
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/click_models.py::compute_ccm_relevance` using pandas group-by on impression logs.

## Benchmark plan

| Size | Impressions | C++ target | Python target |
|---|---|---|---|
| Small | 1k rows | 0.5 ms | 30 ms |
| Medium | 100k rows | 40 ms | 1.5 s |
| Large | 10M rows | 4 s | 90 s |

## Diagnostics
- Raw α value per (q,d) in suggestion detail
- Per-position examination rate plotted on Performance dashboard
- C++/Python badge
- Fallback flag when impression count < threshold
- Debug fields: `n_impressions`, `n_clicks`, `posterior_alpha`

## Edge cases & neutral fallback
- (q,d) with < 20 impressions → neutral α = 0.5 with Beta(1,1) smoothing
- All-zero-clicks (q,d) → α = 1/(N+2) (Laplace)
- Click without preceding impression (data error) → row discarded
- Sessions truncated at 10 results (CCM assumes finite ranked list)

## Minimum-data threshold
At least 20 impressions per (q,d) before α is published; below that fall back to query-mean α.

## Budget
Disk: 5 MB (per-(q,d) α table)  ·  RAM: 50 MB during MLE pass

## Scope boundary vs existing signals
Distinct from `fr013-feedback-driven-explore-exploit-reranking` (Thompson sampling per-suggestion) and `fr016-ga4-suggestion-attribution` (raw GA4 attribution). CCM is the first **position-bias-corrected** behavioural signal in the stack.

## Test plan bullets
- Unit: synthetic log where rank-1 always clicks → α_1 = 1.0
- Unit: rank-3 click never seen → α_3 = small posterior under smoothing
- Parity: C++ vs Python on 100k synthetic rows within 1e-9
- Edge: empty log returns empty α table
- Edge: single-impression (q,d) returns smoothed α only
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
