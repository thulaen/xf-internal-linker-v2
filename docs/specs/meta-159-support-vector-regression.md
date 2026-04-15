# META-159 — Support Vector Regression (SVR)

## Overview
**Category:** Kernel method (supervised regression, ε-insensitive)
**Extension file:** `svr.cpp`
**Replaces/improves:** `sklearn.svm.SVR` for robust non-linear regression with sparse support-vector solutions
**Expected speedup:** ≥3x over libsvm-based sklearn for `n ≤ 5000`
**RAM:** <150 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{n×d}, y ∈ ℝ^n, kernel k, slack C > 0, tube ε ≥ 0
Output: support vectors SV, dual coefs (α − α*), bias b

Primal (ε-insensitive loss):
    min (1/2)·‖w‖² + C·Σ_i (ξ_i + ξ*_i)
    s.t.  y_i − (w·x_i + b) ≤ ε + ξ_i
          (w·x_i + b) − y_i ≤ ε + ξ*_i
          ξ_i, ξ*_i ≥ 0

Dual:
    max  − (1/2)·Σ_{i,j} (α_i − α*_i)(α_j − α*_j)·K(x_i, x_j)
         + Σ_i y_i·(α_i − α*_i) − ε·Σ_i (α_i + α*_i)
    s.t. Σ_i (α_i − α*_i) = 0
         0 ≤ α_i, α*_i ≤ C

Solved by SMO (Sequential Minimal Optimization):
    repeat:
        pick working-set (i, j) by KKT violation
        optimise 2-variable QP in closed form
        update α, α*
        update KKT gradient cache
    until max KKT violation < tol
Prediction:  f(x*) = Σ_{i ∈ SV} (α_i − α*_i)·k(x_i, x*) + b
```

- **Time complexity:** O(n²·d) per sweep; typical 10–50 sweeps empirically (Platt 1998)
- **Space complexity:** O(n²) for cached kernel rows (LRU cache) or O(n) if recomputed
- **Convergence:** Global optimum of convex QP; `tol` cap ensures finite iterations

## Academic Source
Drucker, H., Burges, C. J. C., Kaufman, L., Smola, A., & Vapnik, V. (1996). "Support Vector Regression Machines." *Advances in Neural Information Processing Systems 9 (NIPS)*, 155–161.

## C++ Interface (pybind11)

```cpp
struct SVRModel {
    std::vector<float> support_vectors; // n_sv * d row-major
    std::vector<float> dual_coef;       // n_sv ((α_i − α*_i))
    float bias;
    int n_sv, d;
    char kernel_type[16];
    float gamma, degree, coef0;
};
SVRModel svr_fit(
    const float* X, const float* y, int n, int d,
    const char* kernel, float gamma, float degree, float coef0,
    float C, float epsilon, float tol, int max_iter,
    int cache_size_mb
);
std::vector<float> svr_predict(
    const SVRModel& model,
    const float* X_new, int m
);
```

## Memory Budget
- Runtime RAM: <150 MB for n=5000, cache=100 MB + support vectors
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*d)` for cached SVs; LRU kernel cache via `std::list` + `std::unordered_map`

## Performance Target
- Python baseline: `sklearn.svm.SVR(kernel='rbf', C=C, epsilon=ε).fit(X, y)`
- Target: ≥3x faster via SIMD RBF + SMO with second-order working-set selection
- Benchmark sizes: (n=500, d=32), (n=2000, d=128), (n=5000, d=256)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. SMO is single-threaded; kernel-row prefetch OpenMP-guarded only across independent prediction samples.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. LRU cache bounded by `cache_size_mb`.

**Object lifetime:** Self-assignment safe. No dangling views. SV copy owned by SVRModel.

**Type safety:** Explicit `static_cast` narrowing with comment. `C > 0, ε ≥ 0` validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on cached kernel rows. SLEEF `exp()` for RBF.

**Floating point:** FTZ on init. NaN/Inf entry checks. Double accumulator for gradient updates. Clamp RBF exponent.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`. `f` and `α` arrays 32-byte aligned.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Non-convergence returns `max_iter` reached warning bit.

**Build:** No cyclic includes. Anonymous namespace for kernel cache.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_159.py` | Predictions within 1e-3 of sklearn/libsvm |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥3x faster at all 3 sizes |
| 5 | `pytest test_edges_meta_159.py` | ε=0 (L1 reg), C=∞, n=1, duplicate rows handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- BLAS (`sgemv` for prediction)
- No LAPACK required (closed-form 2-variable QP)

## Pipeline Stage & Non-Conflict
- **Stage:** Reranker (non-linear regression with sparse model)
- **Owns:** Sparse support-vector regression (robust to outliers via ε-tube)
- **Alternative to:** META-158 (KRR — dense solution), META-162 (GPR — probabilistic)
- **Coexists with:** META-160 (Nyström — enables SVR at n > 5k), META-161 (RFF — approximate primal SVR)

## Test Plan
- Linear parity: linear-kernel SVR matches `LinearSVR` within 1e-3
- Sparsity: on clean data, support-vector fraction ≤ 30% of n
- ε-tube behaviour: doubling ε reduces support-vector count monotonically
- Convergence: synthetic separable data hits KKT tol < 1e-3 in ≤ 30 sweeps
- Determinism: same seed + working-set order → identical model
