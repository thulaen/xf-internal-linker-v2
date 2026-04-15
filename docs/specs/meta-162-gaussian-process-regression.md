# META-162 — Gaussian Process Regression (GPR)

## Overview
**Category:** Kernel method (Bayesian regression with uncertainty)
**Extension file:** `gpr.cpp`
**Replaces/improves:** `sklearn.gaussian_process.GaussianProcessRegressor` for link-score calibration with uncertainty estimates
**Expected speedup:** ≥3x over scikit-learn for `n ≤ 3000`
**RAM:** <150 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{n×d}, y ∈ ℝ^n, kernel k(·,·) with hyperparams θ, noise σ²
Output: posterior mean μ*(x*) and variance σ*²(x*) at test points X*

Training:
    K_ij = k(x_i, x_j; θ)                          // n×n
    K_y  = K + σ²·I                                // jitter for PD
    L    = chol(K_y)                               // K_y = L·Lᵀ
    α    = Lᵀ⁻¹·(L⁻¹·y)                            // triangular solves

Prediction for novel X* ∈ ℝ^{m×d}:
    K*  = k(X, X*)        // n×m
    K** = k(X*, X*)       // m×m
    μ*  = K*ᵀ · α
    v   = L⁻¹ · K*
    Σ*  = K** − vᵀ·v                              // posterior covariance

Hyperparameter learning (optional):
    log p(y|X,θ) = −(1/2)·yᵀ·K_y⁻¹·y − (1/2)·log|K_y| − (n/2)·log(2π)
    θ* = argmax log p(y|X,θ)  via L-BFGS on analytical gradient
```

- **Time complexity:** O(n³) Cholesky; O(n·m) per test-point mean; O(n²·m) for full covariance
- **Space complexity:** O(n²) for K and L
- **Convergence:** Exact for fixed θ (closed-form). Hyperparameter optimisation has no global-optimum guarantee — uses multi-start.

## Academic Source
Rasmussen, C. E., & Williams, C. K. I. (2006). *Gaussian Processes for Machine Learning*. MIT Press. ISBN 0-262-18253-X. (Chapter 2 — Regression.)

## C++ Interface (pybind11)

```cpp
struct GPRModel {
    std::vector<float> L;           // n*n lower-triangular Cholesky
    std::vector<float> alpha;       // n
    std::vector<float> X_train;     // n*d (cached)
    std::vector<float> y_mean_shift;
    int n_train, d;
    char kernel_type[16];           // "rbf" | "matern32" | "matern52"
    float length_scale, variance, noise_variance;
    float log_marginal_likelihood;
};
GPRModel gpr_fit(
    const float* X, const float* y, int n, int d,
    const char* kernel,
    float length_scale, float variance, float noise_variance,
    bool optimise_hyperparams, int n_restarts, uint32_t seed
);
// Returns mean (size m) and variance (size m) side-by-side
std::pair<std::vector<float>, std::vector<float>> gpr_predict(
    const GPRModel& model,
    const float* X_new, int m,
    bool return_std
);
```

## Memory Budget
- Runtime RAM: <150 MB for n=3000 (K 36 MB + L 36 MB + multi-start optimiser working set)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*n)`, `alignas(64)` on K and L. n>5000 rejected with `ValueError("use sparse GP or Nyström-GP via META-160")`.

## Performance Target
- Python baseline: `sklearn.gaussian_process.GaussianProcessRegressor(kernel=RBF()).fit(X, y)`
- Target: ≥3x faster via LAPACK `spotrf` Cholesky + manual gradient (no autograd overhead)
- Benchmark sizes: (n=200, d=16), (n=1000, d=64), (n=3000, d=128)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Multi-start restarts use independent worker threads with thread-local RNG; no shared mutable state between restarts.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. `reserve(n*n)` before K fill.

**Object lifetime:** Self-assignment safe. No dangling views. X_train cached copy owned by model.

**Type safety:** Explicit `static_cast` narrowing with comment. `noise_variance ≥ 1e-10` enforced for PD guarantee.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on K, L. SLEEF `exp()` for RBF and Matérn.

**Floating point:** FTZ on init. NaN/Inf entry checks on X and y. Double accumulator for log-det and quadratic form `yᵀ·α`. Adaptive jitter: start at σ²=1e-8·tr(K)/n, double on Cholesky failure up to 6 tries.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`. Triangular solves call BLAS `strsv`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Cholesky failure after max retries raises `LinAlgError("K not PD; increase noise_variance")`.

**Build:** No cyclic includes. Anonymous namespace for kernel + gradient helpers.

**Security:** No `system()`. No `printf(user_string)`. RNG seed documented. Seed=0 rejected.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_162.py` | Posterior mean matches sklearn within 1e-3; std within 5% |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥3x faster than sklearn at all 3 sizes |
| 5 | `pytest test_edges_meta_162.py` | n=1, duplicate rows, negative y, noise→0 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races in multi-start optimiser |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK (`spotrf` Cholesky, `spotrs` triangular solve)
- BLAS (`strsv`, `sgemv`, `sgemm`)
- Internal L-BFGS (shared with META-04 if suitable) — factor out; do not duplicate

## Pipeline Stage & Non-Conflict
- **Stage:** Reranker / score calibration (with uncertainty)
- **Owns:** Bayesian regression on top of any feature representation — provides `(μ, σ)` per prediction
- **Alternative to:** META-158 (KRR — no uncertainty), META-159 (SVR — sparse, no uncertainty)
- **Coexists with:** META-160 (Nyström — enables sparse GP at larger n), META-161 (RFF — approximate GP via random features), META-151 (PCA — reduces d before GP)

## Test Plan
- Noise-free interpolation: training points predicted with σ* ≈ 0 (within 1e-6)
- Calibration: on held-out synthetic data, empirical coverage of 95% CI ≥ 90% and ≤ 98%
- Hyperparameter recovery: synthetic data with known (length_scale, variance) recovered within 10% by optimiser
- PD failure path: degenerate K triggers jitter ladder and either succeeds or raises informative error
- Multi-start determinism: fixed seed across restarts → identical optimum
