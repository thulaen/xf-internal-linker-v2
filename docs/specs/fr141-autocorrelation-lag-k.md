# FR-141 — Autocorrelation Function (ACF) at Lag k

## Overview
The autocorrelation function (ACF) at lag k measures how similar a time series is to a copy of itself shifted by k steps. For forum engagement, ACF at lag 7 reveals weekly habits; ACF at lag 1 reveals day-to-day momentum. FR-141 computes ACF for a small set of operator-chosen lags and exposes them as ranking signals, complementing FR-140 (Fourier, full spectrum) and FR-142 (PACF, partial autocorrelation) by giving a directly interpretable per-lag scalar that operators can read like a temperature gauge.

## Academic source
Box, G. E. P. and Jenkins, G. M. *Time Series Analysis: Forecasting and Control*. Holden-Day, 1976 (revised 1994 with Reinsel; 5th edition Wiley 2015). ISBN: 978-1118675021. (Also: Brockwell, P. J. and Davis, R. A. *Time Series: Theory and Methods*, 2nd ed., Springer, 1991, DOI: 10.1007/978-1-4419-0320-4.)

## Formula
For series `x_1, …, x_n` with sample mean `x̄ = (1/n) Σ x_t`, the sample autocovariance at lag k is

```
γ̂_k = (1/n) · Σ_{t=1..n−k} (x_t − x̄) · (x_{t+k} − x̄)
```

The sample autocorrelation at lag k:

```
ρ̂_k = γ̂_k / γ̂_0
```

where `γ̂_0 = (1/n) Σ (x_t − x̄)² = sample variance`. The biased estimator (divides by n, not n−k) is preferred because it ensures positive semi-definiteness of the resulting Toeplitz matrix.

Asymptotic 95% confidence band under iid null:

```
ρ̂_k ∈ ± 1.96 / √n
```

Bartlett's formula for variance of `ρ̂_k` under more general dependence:

```
Var(ρ̂_k) ≈ (1/n) · Σ_{j=−∞..∞} ( ρ_{j}² + ρ_{j−k} · ρ_{j+k} − 4 ρ_k ρ_j ρ_{j−k} + 2 ρ_j² ρ_k² )
```

## Starting weight preset
```python
"acf_lag_k.enabled": "true",
"acf_lag_k.ranking_weight": "0.0",
"acf_lag_k.lags_to_compute": "1,7,30",
"acf_lag_k.use_fft": "true",
"acf_lag_k.min_observations": "32",
```

## C++ implementation
- File: `backend/extensions/acf_lag_k.cpp`
- Entry: `std::vector<double> acf_lag_k(const double* x, int n, const int* lags, int n_lags)`
- Complexity: direct method O(n · k_max); FFT method O(n log n) via Wiener-Khinchin (FFT, square magnitude, inverse FFT). Use FFT when k_max > log n.
- Thread-safety: pure. SIMD: dot-product per lag vectorisable. Memory: O(n) for centred series + O(k_max) for output.

## Python fallback
`backend/apps/pipeline/services/acf_lag_k.py::compute_acf` (mirrors `statsmodels.tsa.stattools.acf`).

## Benchmark plan
| n samples | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 256 | 4 | <1 | ≥4x |
| 32,768 | 280 | <30 | ≥9x |
| 1,048,576 | 11,500 | <1,000 | ≥11x |

## Diagnostics
UI: small inline chip "ρ_7 = 0.62 (sig)" / "ρ_1 = 0.05". Debug fields per lag: `acf_value`, `acf_ci_low`, `acf_ci_high`, `acf_significant`, `n_observations_used`, `lag_in_days`, `method` ("direct" or "fft").

## Edge cases & neutral fallback
n < min_observations → neutral, all `ρ̂_k = 0`. Constant series → `γ̂_0 = 0`, ACF undefined; return 0 with state `neutral_zero_variance`. NaN values: drop and recompute (state flag set). Lag k ≥ n: invalid, raise ValueError. Lag k = 0 always returns 1.0 by definition. FFT method requires zero-padding to length 2n−1.

## Minimum-data threshold
n ≥ 4 · k_max. Below this, `ρ̂_k` estimates have high variance and are reported but flagged as low-confidence.

## Budget
Disk: <1 MB  ·  RAM: <12 MB per page (FFT buffers freed; centred series freed)

## Scope boundary vs existing signals
FR-140 (Fourier) gives the full spectrum; FR-141 gives ACF at a small chosen set of lags — easier to reason about. FR-142 (PACF) removes the influence of intermediate lags, giving the *direct* effect of lag k. FR-143 (EWMA) is a smoothing method, not a correlation measure. FR-141's lag-1 value is the "momentum" of a series; FR-140 cannot answer this scalar question without further analysis.

## Test plan bullets
- AR(1) process `x_t = 0.7 x_{t−1} + ε_t` → ρ̂_1 ≈ 0.7, ρ̂_2 ≈ 0.49.
- White noise → all ρ̂_k near 0, within ±1.96/√n band 95% of the time.
- Periodic signal period 7 → ρ̂_7 high, ρ̂_3 low.
- Constant series → neutral fallback, no division-by-zero.
- Lag 0 returns exactly 1.0.
- NaN values dropped, no crash.
- Direct vs FFT method: identical results within float epsilon.
- Compare against `statsmodels.tsa.stattools.acf` with `unbiased=False`: identical values.
