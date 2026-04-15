# FR-137 — STL Seasonal-Trend Decomposition

## Overview
Many forum threads have weekly or annual seasonality (a tax thread peaks in March; a fantasy-football thread peaks in September). STL decomposition separates a page's engagement series into trend, seasonal, and remainder components, complementing FR-050 (seasonality temporal demand) by giving an *additive decomposition* that exposes the trend-only component. The trend component, free of weekly noise, is a cleaner long-term popularity signal than raw counts.

## Academic source
Cleveland, R. B., Cleveland, W. S., McRae, J. E., and Terpenning, I. "STL: A seasonal-trend decomposition procedure based on LOESS." *Journal of Official Statistics*, 6(1), pp. 3–73, 1990. (No DOI; available at https://www.scb.se/contentassets/ca21efb41fee47d293bbee5bf7be7fb3/stl-a-seasonal-trend-decomposition-procedure-based-on-loess.pdf)

## Formula
For series `Y_t = T_t + S_t + R_t` with seasonal period `n_p`, STL iterates two nested loops. Inner loop (one pass):

```
1. Detrending:        Y_t − T_t^{(k)}
2. Cycle-subseries smoothing (LOESS, span n_s) → C_t
3. Low-pass filter:   L_t = LOESS( moving_avg(C_t, n_p, n_p, 3) )
4. Seasonal:          S_t^{(k+1)} = C_t − L_t
5. Deseasonalising:   Y_t − S_t^{(k+1)}
6. Trend smoothing (LOESS, span n_t) → T_t^{(k+1)}
```

Outer loop weights observations by robustness weights `ρ_t = B(|R_t| / (6 · median|R|))`, where `B(u) = (1 − u²)²` for `|u| < 1`, else 0. LOESS at point `x` solves the weighted least squares

```
β̂ = argmin Σ_i w_i(x) · (y_i − β_0 − β_1 (x_i − x))²
w_i(x) = T(|x_i − x| / d) · ρ_i
T(u) = (1 − u³)³        for |u| < 1
```

with `d = ` distance to the q-th nearest neighbour (`q = span × n`). Final remainder: `R_t = Y_t − T_t − S_t`. Trend strength: `F_T = max(0, 1 − Var(R) / Var(R + T))`.

## Starting weight preset
```python
"stl_decomposition.enabled": "true",
"stl_decomposition.ranking_weight": "0.0",
"stl_decomposition.period_n_p": "7",
"stl_decomposition.seasonal_span_n_s": "13",
"stl_decomposition.trend_span_n_t": "21",
"stl_decomposition.outer_iterations": "1",
"stl_decomposition.inner_iterations": "2",
```

## C++ implementation
- File: `backend/extensions/stl_decomposition.cpp`
- Entry: `STLResult stl_decompose(const double* y, int n, int period, int n_s, int n_t, int n_o, int n_i)`
- Complexity: O(n_o · n_i · n · (n_s + n_t)) ≈ O(n) for fixed spans. Three n-length output vectors.
- Thread-safety: pure. SIMD: LOESS weighted regression vectorised across the local neighbourhood. Memory: ~6n doubles. `alignas(64)` on hot arrays.

## Python fallback
`backend/apps/pipeline/services/stl_decomposition.py::stl_decompose` (mirrors `statsmodels.tsa.seasonal.STL`).

## Benchmark plan
| n samples | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 365 | 45 | <6 | ≥7x |
| 36,500 | 4,500 | <500 | ≥9x |
| 365,000 | 480,000 | <50,000 | ≥9x |

## Diagnostics
UI: three-panel chart (trend, seasonal, remainder) per page on demand. Debug fields: `trend_strength_F_T`, `seasonal_strength_F_S`, `current_trend_value`, `current_seasonal_index`, `iteration_count`, `loess_span_used`.

## Edge cases & neutral fallback
n < 2 · period → cannot decompose, neutral fallback. Constant series → trend = constant, seasonal = 0, remainder = 0. Missing values → linear-interpolate before decomposition (flag in diagnostics). Period not detected → user supplies; if absent, return neutral. Convergence: STL is non-iterative in inner loop (fixed `n_i` passes), so always terminates.

## Minimum-data threshold
At least 2 full seasonal cycles (`n ≥ 2 · n_p`); 4 cycles preferred for robust estimates.

## Budget
Disk: <1 MB  ·  RAM: <24 MB per page (freed post-decomposition)

## Scope boundary vs existing signals
FR-050 (seasonality temporal demand) measures *whether* a topic is in-season; FR-137 *decomposes* the entire history into orthogonal components and exposes a clean trend signal that FR-050 cannot. FR-138 (Mann-Kendall) tests trend significance; FR-137 estimates trend value and shape.

## Test plan bullets
- Synthetic `T_t + sin(2πt/7) + N(0,1)` → recovered trend has Pearson r > 0.99 with true `T_t`.
- Pure trend (no seasonal) → recovered seasonal component near zero everywhere.
- Pure seasonal (no trend) → recovered trend is approximately constant.
- Constant series → trend = constant, seasonal = 0, no division-by-zero.
- NaN values interpolated before decomposition, flag set in diagnostics.
- Output: `Y_t = T_t + S_t + R_t` exactly within float epsilon.
- `period = 1` raises ValueError.
- `n < 2 · period` returns neutral fallback.
