# FR-139 — Theil-Sen Robust Slope Estimator

## Overview
Ordinary least squares (OLS) regression is destroyed by a few outlier points — and forum engagement series are *full* of outlier days (one viral hit, one Reddit submission). Theil-Sen estimates the slope as the *median* of all pairwise slopes, which tolerates up to 29.3% outliers. FR-139 produces a robust per-page engagement-trend slope that complements FR-138 (which only tests significance, not magnitude). The slope's sign and magnitude feed directly into the freshness-velocity ranking component.

## Academic source
Theil, H. "A rank-invariant method of linear and polynomial regression analysis, I, II, III." *Proceedings of the Royal Netherlands Academy of Sciences*, 53, pp. 386–392, 521–525, 1397–1412, 1950. Sen, P. K. "Estimates of the regression coefficient based on Kendall's tau." *Journal of the American Statistical Association*, 63(324), pp. 1379–1389, 1968. DOI: 10.1080/01621459.1968.10480934.

## Formula
For pairs `(t_i, x_i), i = 1..n`, the Theil-Sen slope is

```
β̂ = median_{i < j} ( (x_j − x_i) / (t_j − t_i) )
```

over all `C(n, 2) = n(n−1)/2` distinct index pairs with `t_j ≠ t_i`. The intercept is

```
α̂ = median_i ( x_i − β̂ · t_i )
```

A two-sided 100(1−α)% confidence interval for `β̂` is obtained from the order statistics of pairwise slopes via Kendall's tau:

```
N = n(n−1)/2
C_α = z_{1−α/2} · √( n(n−1)(2n+5) / 18 )
M_lower = (N − C_α) / 2
M_upper = (N + C_α) / 2
β̂_low  = slope_{(M_lower)}
β̂_high = slope_{(M_upper)}
```

where `slope_{(k)}` is the k-th order statistic of the sorted pairwise slopes.

## Starting weight preset
```python
"theil_sen.enabled": "true",
"theil_sen.ranking_weight": "0.0",
"theil_sen.alpha_confidence": "0.05",
"theil_sen.min_observations": "10",
"theil_sen.window_days": "30",
```

## C++ implementation
- File: `backend/extensions/theil_sen.cpp`
- Entry: `TheilSenResult theil_sen(const double* t, const double* x, int n, double alpha)`
- Complexity: naive O(n²) generates pairs then quickselects median in O(n²) time, O(n²) memory. For n > 5000, use the Cole et al. randomised O(n log n) algorithm. Default implementation: O(n²) up to n = 5000.
- Thread-safety: pure. SIMD: pairwise slope generation vectorisable across i,j pairs. Memory: `n²/2` doubles for slope array (free after quickselect).

## Python fallback
`backend/apps/pipeline/services/theil_sen.py::theil_sen_slope` (mirrors `scipy.stats.theilslopes`).

## Benchmark plan
| n samples | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 100 | 12 | <1 | ≥12x |
| 1,000 | 1,200 | <100 | ≥12x |
| 5,000 | 28,000 | <2,500 | ≥11x |

## Diagnostics
UI: numeric slope ("+0.85 clicks/day") with confidence band ("[0.42, 1.31]"). Debug fields: `slope_beta_hat`, `intercept_alpha_hat`, `slope_ci_low`, `slope_ci_high`, `n_pairs_used`, `breakdown_point_used`, `outlier_fraction_estimate`.

## Edge cases & neutral fallback
n < min_observations → neutral, slope = 0. All `t_i` identical → no valid pairs, neutral. All `x_i` identical → slope = 0 exactly, CI = [0, 0]. NaN values dropped pre-computation. Pairs with `t_j = t_i` (duplicate timestamps) skipped. n > 5000 → switch to randomised O(n log n) algorithm to keep memory under budget. Quickselect is in-place to avoid full sort.

## Minimum-data threshold
At least 10 observations and at least 5 distinct timestamps to form meaningful pairs.

## Budget
Disk: <1 MB  ·  RAM: <100 MB at n=5000 (n²/2 = 12.5M slopes × 8B = 100MB); switches to randomised algorithm beyond this.

## Scope boundary vs existing signals
FR-138 (Mann-Kendall) tests trend *significance*; FR-139 estimates trend *magnitude*. They are paired but distinct — Mann-Kendall says "yes/no", Theil-Sen says "how much per day, with what uncertainty". FR-080 (freshness decay) is a closed-form recency function, not an estimated slope.

## Test plan bullets
- `x_t = 2t + N(0, 0.5)` → β̂ ≈ 2.0 within ±0.05.
- Inject 25% outliers at 10× magnitude → slope still recovered within ±0.1 (breakdown property).
- Constant series → β̂ = 0, CI = [0, 0].
- Single-point series → neutral fallback.
- Compare against `scipy.stats.theilslopes`: identical β̂, α̂, CI within float epsilon.
- n = 5000 → memory under 100 MB, time under 3 seconds.
- Duplicate timestamps skipped, no division-by-zero.
- Slope CI brackets β̂ for `α = 0.05` in 95% of synthetic trials.
