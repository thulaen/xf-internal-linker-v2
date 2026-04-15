# FR-138 — Mann-Kendall Non-Parametric Trend Test

## Overview
The Mann-Kendall test asks "is there a monotonic trend in this time series?" without assuming any distribution shape. Forum-engagement series are heavy-tailed and noisy, so a *non-parametric* trend test is more robust than fitting a regression slope. FR-138 complements FR-139 (Theil-Sen, which estimates slope magnitude) by providing a *significance* score (p-value) that gates whether the trend is real or just noise. Pages with statistically significant upward trends rank higher; those with no trend or downward trend rank lower.

## Academic source
Mann, H. B. "Nonparametric tests against trend." *Econometrica*, 13(3), pp. 245–259, 1945. DOI: 10.2307/1907187. (Also Kendall, M. G. *Rank Correlation Methods*, Griffin, 1948.)

## Formula
For series `x_1, …, x_n`, Mann-Kendall statistic:

```
S = Σ_{i=1..n−1} Σ_{j=i+1..n} sgn(x_j − x_i)

sgn(d) = +1   if d > 0
         0    if d = 0
         −1   if d < 0
```

Variance of S under the null hypothesis of no trend (with ties):

```
Var(S) = [ n(n−1)(2n+5) − Σ_{p} t_p (t_p − 1)(2 t_p + 5) ] / 18
```

where `t_p` is the number of observations in the p-th group of tied values. Standardised statistic:

```
Z = (S − 1) / √Var(S)    if S > 0
    0                    if S = 0
    (S + 1) / √Var(S)    if S < 0
```

Two-sided p-value: `p = 2 · (1 − Φ(|Z|))`. Trend significant at level `α` if `p < α`. The continuity correction `±1` removes bias for finite n.

## Starting weight preset
```python
"mann_kendall.enabled": "true",
"mann_kendall.ranking_weight": "0.0",
"mann_kendall.alpha": "0.05",
"mann_kendall.min_observations": "10",
"mann_kendall.window_days": "60",
```

## C++ implementation
- File: `backend/extensions/mann_kendall.cpp`
- Entry: `MannKendallResult mann_kendall(const double* x, int n)`
- Complexity: O(n log n) using merge-sort-based inversion counting (avoids naive O(n²) double loop). Tie correction: O(n log n) for sort + linear pass.
- Thread-safety: pure. SIMD: not effective for the conditional `sgn` test; merge-sort is the bottleneck. Memory: O(n) for sort buffer.

## Python fallback
`backend/apps/pipeline/services/mann_kendall.py::mann_kendall_test` (mirrors `pymannkendall.original_test`).

## Benchmark plan
| n samples | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 100 | 18 | <2 | ≥9x |
| 10,000 | 1,800 | <200 | ≥9x |
| 1,000,000 | 220,000 | <22,000 | ≥10x |

## Diagnostics
UI: trend arrow (up/down/flat) with confidence chip (e.g., "p=0.02"). Debug fields: `mk_S`, `mk_variance`, `mk_Z`, `mk_p_value`, `trend_direction`, `trend_significant`, `tie_groups`.

## Edge cases & neutral fallback
n < min_observations → neutral, `score = 0.5`, state `neutral_insufficient_data`. All values identical → S = 0, Z = 0, no significant trend. NaN values dropped before computation (state flag set). For very small n (< 10), use exact distribution table instead of normal approximation. Var(S) = 0 → no variance to test, neutral fallback.

## Minimum-data threshold
At least 10 observations within the window. Below 10, the normal approximation degrades and the exact-distribution table should be used (or neutral fallback).

## Budget
Disk: <1 MB  ·  RAM: <12 MB per page (sort buffer freed after test)

## Scope boundary vs existing signals
FR-007/FR-080 are decay functions of *time since publish/update*; they don't test for trend in any signal. FR-135 (PELT) detects abrupt changes; FR-138 detects gradual monotonic trends. FR-139 (Theil-Sen) estimates the slope magnitude; FR-138 tests whether *any* slope is statistically distinguishable from zero.

## Test plan bullets
- Pure increasing series `x_t = t` → S = n(n−1)/2, p < 1e−6.
- Pure decreasing series → S = −n(n−1)/2, p < 1e−6.
- Random Gaussian noise → p > 0.05 in 95% of trials.
- Constant series → S = 0, Z = 0, p = 1.0.
- Series with NaNs → cleaned, flag set, no crash.
- Tied values → tie correction applied to Var(S).
- Compare against `pymannkendall.original_test`: identical S, Z, p within float epsilon.
- n < 10 → neutral fallback, no normal approximation used.
