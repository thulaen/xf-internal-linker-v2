# FR-164 — User Browsing Model (UBM)

## Overview
The User Browsing Model conditions examination on both the rank `i` and the distance `r` from the previous click, capturing the realistic behaviour where a user re-anchors their attention after every click. UBM consistently outperforms position-bias and cascade models on commercial click logs. Complements `fr165-position-bias-model` because PBM assumes examination depends only on rank while UBM also depends on click history.

## Academic source
Full citation: **Dupret, G. & Piwowarski, B. (2008).** "A User Browsing Model to Predict Search Engine Click Data from Past Observations." *Proceedings of the 31st ACM SIGIR Conference on Research and Development in Information Retrieval*, pp. 331-338. DOI: `10.1145/1390334.1390392`.

## Formula
Dupret & Piwowarski (2008), Equations 1-3:

```
P(C_i = 1 | q, d_i, r) = β_{i, r} · γ_{q, d_i}

where
  β_{i, r}  = P(E_i = 1 | i, r) = examination prior conditioned on rank i
              and distance r from the previously clicked rank
              (r = i for "no prior click")
  γ_{q,d_i} = perceived relevance of (q, d_i)
```

Parameters fitted via EM. The β table is small (10 ranks × 10 distances = 100 cells) and is shared across queries, while γ is per-(q,d).

## Starting weight preset
```python
"ubm.enabled": "true",
"ubm.ranking_weight": "0.0",
"ubm.max_rank": "10",
"ubm.em_max_iters": "20",
```

## C++ implementation
- File: `backend/extensions/ubm.cpp`
- Entry: `UBMParams ubm_em(const ImpressionLog& log, int max_rank, int max_iters)`
- Complexity: O(I · L · K) per EM iter; same big-O as DBN but with smaller per-row work
- Thread-safety: per-thread E-step accumulators
- Builds via pybind11

## Python fallback
`backend/apps/pipeline/services/click_models.py::ubm_em` using numpy.

## Benchmark plan

| Size | Impressions | C++ target | Python target |
|---|---|---|---|
| Small | 1k rows | 4 ms | 150 ms |
| Medium | 100k rows | 350 ms | 22 s |
| Large | 10M rows | 35 s | 22 min |

## Diagnostics
- β heatmap (rank × distance) on Performance dashboard
- Per-(q,d) γ value in suggestion detail
- C++/Python badge
- Fallback flag
- Debug fields: `em_iters_used`, `final_loglik`, `beta_table_norm`

## Edge cases & neutral fallback
- (q,d) with no impressions → γ neutral 0.5
- Sessions with no clicks → distance r = rank for every position
- Sessions truncated at `max_rank`
- EM convergence checked via Δ-log-likelihood < 1e-4

## Minimum-data threshold
At least 30 impressions per (q,d) before γ is published; otherwise fallback to PBM.

## Budget
Disk: 5 MB γ table + 1 KB β table  ·  RAM: 200 MB during EM

## Scope boundary vs existing signals
Distinct from `fr162-cascade-click-model` (no distance conditioning), `fr163-dbn-click-model` (no satisfaction state), `fr165-position-bias-model` (no click-history conditioning). UBM is the only model that uses distance-from-previous-click.

## Test plan bullets
- Unit: synthetic log where users always click rank 1 → γ_1 ≈ 1.0, β_{1,1} ≈ 1.0
- Unit: clicks decay with distance → β_{i,r} monotonically decreasing in r
- Parity: C++ vs Python EM within 1e-3 on 10k rows
- Edge: empty log returns prior parameters
- Edge: max_rank cap respected on long sessions
- Integration: contributes only when enabled
- Regression: ranking unchanged when weight = 0.0
