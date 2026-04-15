# FR-135 — PELT Change-Point Detection

## Overview
Forum topics shift their character over time (a thread originally about cars pivots to insurance regulation; a tag's audience changes after a moderation policy update). PELT (Pruned Exact Linear Time) detects these shifts in any time-indexed signal, complementing the existing recency and freshness signals (FR-007, FR-080) by labelling pages that have *just* undergone a structural break in their engagement, click, or update profile. Pages with a recent change-point may be in a new equilibrium and deserve different ranking treatment.

## Academic source
Killick, R., Fearnhead, P., and Eckley, I. A. "Optimal detection of changepoints with a linear computational cost." *Journal of the American Statistical Association*, 107(500), pp. 1590–1598, 2012. DOI: 10.1080/01621459.2012.737745.

## Formula
For a series `y_{1:n}` and segment cost function `C(·)`, find segmentation `τ_0 = 0 < τ_1 < … < τ_m < τ_{m+1} = n` minimising

```
F(n) = min_{m, τ_{1:m}}  Σ_{i=0..m} [ C(y_{τ_i+1 : τ_{i+1}}) + β ]
```

where `β > 0` is the per-changepoint penalty (BIC: `β = k · ln n` with `k` parameters per segment). PELT recursion:

```
F(t) = min_{τ ∈ R_t} [ F(τ) + C(y_{τ+1:t}) + β ]
R_t = { τ ∈ R_{t−1} ∪ {t−1} : F(τ) + C(y_{τ+1:t}) ≤ F(t) }
```

The pruning condition `R_t` discards candidates that can never become optimal, giving expected O(n) cost when changepoints occur at a positive rate. Default segment cost (Gaussian, unknown mean and variance):

```
C(y_{a:b}) = (b − a + 1) · ln σ̂²_{a:b}
```

## Starting weight preset
```python
"pelt_changepoint.enabled": "true",
"pelt_changepoint.ranking_weight": "0.0",
"pelt_changepoint.penalty_beta": "log_n",
"pelt_changepoint.min_segment_length": "5",
"pelt_changepoint.recency_window_days": "30",
```

## C++ implementation
- File: `backend/extensions/pelt_changepoint.cpp`
- Entry: `std::vector<int> pelt_changepoint(const double* y, int n, double beta, int min_seg, CostKind kind)`
- Complexity: expected O(n), worst case O(n²); pruning set stored as `std::vector<int>` with in-place compaction.
- Thread-safety: pure. Memory: 3·n doubles for `F`, prefix sums, prefix square sums; freed before return. No SIMD needed (linear scan).

## Python fallback
`backend/apps/pipeline/services/pelt_changepoint.py::detect_changepoints` (uses `ruptures.Pelt` as reference).

## Benchmark plan
| n samples | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 500 | 22 | <3 | ≥7x |
| 50,000 | 2,400 | <300 | ≥8x |
| 5,000,000 | 280,000 | <30,000 | ≥9x |

## Diagnostics
UI: timeline marker on the page-history chart at every detected change-point. Debug fields: `changepoint_indices`, `segment_means`, `segment_variances`, `last_changepoint_age_days`, `recent_change_detected` (bool), `total_cost_F_n`.

## Edge cases & neutral fallback
n < 2·min_seg → no changepoints, neutral 0.5. Constant series → zero variance → use ε=1e-9 to avoid `ln 0`. NaN values in `y` → drop those indices and pass cleaned vector. Penalty `β` too small → over-segmentation; too large → no changepoints. Pruning set never empty (always retains current candidate). Convergence not iterative — exact in one pass.

## Minimum-data threshold
At least 30 observations before PELT runs (otherwise neutral). At least one segment must satisfy `min_segment_length` or the result is rejected.

## Budget
Disk: <1 MB  ·  RAM: <16 MB per page (freed after detection)

## Scope boundary vs existing signals
FR-007 and FR-080 model decay around a *known* event (publication or last update). FR-135 *discovers* unknown events from data. FR-138 (Mann-Kendall) tests monotonic trend; FR-135 detects *abrupt* shifts and is non-monotonic.

## Test plan bullets
- Synthetic mean-shift at t=300 in length-600 series → changepoint detected within ±3 indices.
- Stationary series → zero changepoints.
- Increasing penalty `β` → fewer changepoints (monotonic).
- Constant series → no changepoints, no division-by-zero.
- Series with NaNs → cleaned then processed, no crash.
- Compare against `ruptures.Pelt` reference: identical changepoint set within 1-index tolerance.
- Multiple variance shifts → all detected with Gaussian cost.
- `min_segment_length = 1` and `min_segment_length = n/4` both produce valid segmentations.
