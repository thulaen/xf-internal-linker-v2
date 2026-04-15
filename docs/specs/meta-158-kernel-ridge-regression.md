# META-158 — Kernel Ridge Regression (KRR)

## Overview
**Category:** Kernel method (supervised regression)
**Extension file:** `kernel_ridge.cpp`
**Replaces/improves:** `sklearn.kernel_ridge.KernelRidge` for non-linear link-score regression on small/medium training sets
**Expected speedup:** ≥4x over scikit-learn for `n ≤ 5000`
**RAM:** <150 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{n×d}, y ∈ ℝ^n, kernel k(·,·), λ > 0
Output: dual coefficients α ∈ ℝ^n, prediction function f(x*)

Training:
    K_ij = k(x_i, x_j)                          // n×n Gram matrix
    α   = (K + λ·I)⁻¹ · y                       // solve via Cholesky

Prediction for novel x*:
    f(x*) = Σ_i α_i · k(x_i, x*)

Solved via Cholesky:
    K + λ·I = L·Lᵀ            (L lower-triangular)
    solve L·z = y             via forward-substitution
    solve Lᵀ·α = z            via back-substitution
```

- **Time complexity:** O(n²·d) to form K, O(n³/3) for Cholesky, O(n·d) per prediction
- **Space complexity:** O(n²) dominated by Gram matrix
- **Convergence:** Exact (closed-form); regularisation λ > 0 guarantees positive-definite K+λI

## Academic Source
Saunders, C., Gammerman, A., & Vovk, V. (1998). "Ridge Regression Learning Algorithm in Dual Variables." *Proceedings of the 15th International Conference on Machine Learning (ICML)*, 515–521.

## C++ Interface (pybind11)

```cpp
struct KRRModel {
    std::vector<float> alpha;         // n dual coefficients
    std::vector<float> X_train;       // n*d row-major (cached for prediction)
    int n_train, d;
    char kernel_type[16];             // "rbf" | "poly" | "linear"
    float gamma, degree, coef0;
};
KRRModel krr_fit(
    const float* X, const float* y, int n, int d,
    const char* kernel, float gamma, float degree, float coef0,
    float lambda_reg
);
std::vector<float> krr_predict(
    const KRRModel& model,
    const float* X_new, int m
);
```

## Memory Budget
- Runtime RAM: <150 MB for n=5000 (Gram 100 MB + Cholesky in-place)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*n)`, `alignas(64)` on Gram

## Performance Target
- Python baseline: `sklearn.kernel_ridge.KernelRidge(kernel='rbf', alpha=λ).fit(X, y)`
- Target: ≥4x faster via SIMD RBF + LAPACK `spotrf` Cholesky
- Benchmark sizes: (n=500, d=32), (n=2000, d=128), (n=5000, d=256)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Gram construction OpenMP with `schedule(static)` for cache locality.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. `reserve(n*n)` before fill. n>10000 rejected with `ValueError("use Nyström, META-160")`.

**Object lifetime:** Self-assignment safe. No dangling views. X_train copy owned by KRRModel.

**Type safety:** Explicit `static_cast` narrowing with comment. Kernel enum validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on Gram. SLEEF `exp()` for RBF.

**Floating point:** FTZ on init. NaN/Inf entry checks on X and y. Double accumulator for K row sums. Clamp RBF exponent to [−50, 0].

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Cholesky failure (not PD even with λ>0) raises `LinAlgError` with λ-suggestion.

**Build:** No cyclic includes. Anonymous namespace for kernel dispatch.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_158.py` | Predictions match sklearn within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥4x faster at all 3 sizes |
| 5 | `pytest test_edges_meta_158.py` | n=1, duplicate rows, λ=0 failure, huge λ handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK (`spotrf` Cholesky, `spotrs` triangular solve)
- BLAS (`sgemv` for prediction)

## Pipeline Stage & Non-Conflict
- **Stage:** Reranker / calibration (non-linear regression on link scores)
- **Owns:** Small-data kernel regression with closed-form solution
- **Alternative to:** META-159 (SVR — sparse solution), META-162 (GPR — Bayesian)
- **Coexists with:** META-160 (Nyström — swaps in approximated K for large n), META-161 (RFF — approximates same RBF kernel in primal space)

## Test Plan
- Linear kernel parity: matches ordinary ridge regression within 1e-5
- Perfect fit: λ → 0 on non-singular K recovers training labels
- Huge λ degeneracy: predictions tend to `mean(y)` as λ → ∞
- Unknown kernel string: raises `ValueError`
- NaN y input: raises `ValueError` before Cholesky
