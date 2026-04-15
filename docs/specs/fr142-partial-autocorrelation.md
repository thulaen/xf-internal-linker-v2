# FR-142 — Partial Autocorrelation Function (PACF)

## Overview
ACF at lag 7 is high partly because lag-1, lag-2, …, lag-6 correlations cascade through the series. Partial autocorrelation (PACF) strips out those intermediate lags and reports the *direct* dependence of `x_t` on `x_{t−k}` after controlling for `x_{t−1}, …, x_{t−k+1}`. PACF is the canonical tool for choosing autoregressive (AR) model order. FR-142 complements FR-141 (ACF) by giving the cleaner, decorrelated lag-k signal — useful for identifying weekly cycles that aren't just a propagation of daily momentum.

## Academic source
Box, G. E. P. and Jenkins, G. M. *Time Series Analysis: Forecasting and Control*. Holden-Day, 1976. Durbin-Levinson recursion for efficient PACF computation: Durbin, J. "The fitting of time-series models." *Revue de l'Institut International de Statistique*, 28(3), pp. 233–244, 1960. DOI: 10.2307/1401322. Levinson, N. "The Wiener RMS error criterion in filter design and prediction." *Journal of Mathematics and Physics*, 25, pp. 261–278, 1947. DOI: 10.1002/sapm1946251261.

## Formula
For lag k, the PACF is the coefficient `φ_{k,k}` in the AR(k) regression

```
x_t = φ_{k,1} x_{t−1} + φ_{k,2} x_{t−2} + … + φ_{k,k} x_{t−k} + ε_t
```

estimated from the autocorrelations `ρ̂_1, …, ρ̂_k` via the Durbin-Levinson recursion:

```
Initialise:
  φ_{1,1} = ρ̂_1
  σ²_1   = (1 − ρ̂_1²) · γ̂_0

For m = 2..k:
  φ_{m,m} = ( ρ̂_m − Σ_{j=1..m−1} φ_{m−1,j} · ρ̂_{m−j} ) / ( 1 − Σ_{j=1..m−1} φ_{m−1,j} · ρ̂_j )
  φ_{m,j} = φ_{m−1,j} − φ_{m,m} · φ_{m−1,m−j}    for j = 1..m−1
  σ²_m   = σ²_{m−1} · (1 − φ_{m,m}²)
```

The PACF at lag k is `φ̂_k = φ_{k,k}`. Asymptotic 95% confidence band under iid null:

```
φ̂_k ∈ ± 1.96 / √n
```

## Starting weight preset
```python
"pacf_lag_k.enabled": "true",
"pacf_lag_k.ranking_weight": "0.0",
"pacf_lag_k.lags_to_compute": "1,7,30",
"pacf_lag_k.method": "durbin_levinson",
"pacf_lag_k.min_observations": "50",
```

## C++ implementation
- File: `backend/extensions/pacf_lag_k.cpp`
- Entry: `std::vector<double> pacf_lag_k(const double* acf, int n_acf, const int* lags, int n_lags, int n_obs)`
- Complexity: Durbin-Levinson is O(k_max²); much faster than Yule-Walker O(k³) matrix solve. Total with ACF: O(n log n + k_max²).
- Thread-safety: pure. SIMD: inner products in the recursion vectorisable. Memory: O(k_max) for `φ_{m,j}` rows (rolling pair).

## Python fallback
`backend/apps/pipeline/services/pacf_lag_k.py::compute_pacf` (mirrors `statsmodels.tsa.stattools.pacf` with `method='ywm'`).

## Benchmark plan
| n samples | Python (ms) | C++ target (ms) | Speedup |
|---|---|---|---|
| 256 | 5 | <1 | ≥5x |
| 32,768 | 320 | <40 | ≥8x |
| 1,048,576 | 14,000 | <1,200 | ≥11x |

## Diagnostics
UI: per-lag chip "φ̂_7 = 0.18 (sig)". Debug fields per lag: `pacf_value`, `pacf_ci_low`, `pacf_ci_high`, `pacf_significant`, `recursion_iterations`, `recursion_residual_variance`, `lag_in_days`.

## Edge cases & neutral fallback
n < min_observations → neutral, all `φ̂_k = 0`. Constant series → ACF undefined → PACF undefined; return neutral. Recursion denominator near zero (`1 − Σ φ_{m−1,j} ρ̂_j ≈ 0`) → numerical instability; return neutral with state `neutral_singular_recursion`. Lag k ≥ n → ValueError. Lag 0 always 1.0 by definition. ACF must be finite and `|ρ̂_k| < 1` for all k ≤ k_max.

## Minimum-data threshold
n ≥ 50 for stable PACF estimates at moderate lags; recommend n ≥ 5 · k_max.

## Budget
Disk: <1 MB  ·  RAM: <8 MB per page (recursion buffers freed; ACF reused if FR-141 cached)

## Scope boundary vs existing signals
FR-141 (ACF) reports total correlation including indirect effects; FR-142 reports the *direct* effect at lag k. AR(p) model order: PACF cuts off after p, ACF tails off — these are dual diagnostics. FR-140 (Fourier) is frequency-domain; FR-142 is time-domain. FR-143 (EWMA) is a smoothing algorithm with no correlation interpretation.

## Test plan bullets
- AR(1) process `x_t = 0.8 x_{t−1} + ε_t` → φ̂_1 ≈ 0.8, φ̂_2 ≈ 0, φ̂_k ≈ 0 for k ≥ 2 (cutoff property).
- AR(2) process → φ̂_1 and φ̂_2 non-zero, φ̂_k ≈ 0 for k ≥ 3.
- White noise → all φ̂_k within ±1.96/√n band.
- Constant series → neutral fallback.
- Singular recursion (highly collinear ACF) → caught and neutral fallback.
- Lag 0 returns 1.0.
- Compare against `statsmodels.tsa.stattools.pacf(method='ywm')`: identical within float epsilon.
- NaN ACF input → ValueError, no crash.
