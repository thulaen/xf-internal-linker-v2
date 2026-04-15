# META-224 — Recursive Feature Elimination (RFE)

## Overview
**Category:** Feature selection (wrapper)
**Extension file:** `rfe.cpp`
**Replaces/improves:** Manual feature drop in `feature_engineering.py`
**Expected speedup:** ≥4x over sklearn `RFE` Python wrapper
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

Iteratively remove the feature with the smallest linear-model coefficient magnitude (Guyon et al. 2002).

```
Input: feature matrix X ∈ ℝ^{n×d}, labels y, target count k, step size r
Output: ranking of features by elimination order; top-k selected

S ← {1..d}                                           (active feature set)
ranking ← empty array of size d
while |S| > k:
    fit linear model on X[:, S] → coefficients w
    find r features in S with smallest |w_j|
    for each f in those r features:
        ranking[f] ← |S|                             (record elimination rank)
        S ← S \ {f}
for each f in S:
    ranking[f] ← 0                                   (survivors tied at top)
return ranking, top-k = S
```

- **Time complexity:** O((d−k)/r · fit_cost) — fit_cost = O(n·d²) for OLS
- **Space complexity:** O(n·d) for X + O(d) for coefficients/ranking
- **Convergence:** Deterministic — fixed elimination schedule

## C++ Interface (pybind11)

```cpp
// RFE with ridge-regularized linear model; returns feature ranking
std::vector<int> rfe_select(
    const float* X, int n, int d,
    const float* y,
    int target_k, int step_size,
    float ridge_lambda, int max_iter
);
```

## Memory Budget
- Runtime RAM: <30 MB (X copy + working coefficient vector)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n * d)`

## Performance Target
- Python baseline: `sklearn.feature_selection.RFE(LogisticRegression)`
- Target: ≥4x faster (batched coefficient warm-start, no Python per-iter overhead)
- Benchmark: n=10k × d ∈ {50, 200, 1000} features, step=1 and step=d/10

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Ridge regularization to avoid singular normal equations. Double accumulator for coefficient norms.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_224.py` | Ranking matches sklearn RFE exactly for step=1 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than sklearn reference |
| 5 | `pytest test_edges_meta_224.py` | d=k, d=1, NaN column, constant column pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Linear-model fit (reuse coordinate-descent or small Cholesky solver)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-training feature selection (before ranker fit)
- **Owns:** Wrapper-based ranking by coefficient magnitude
- **Alternative to:** META-226 mRMR, META-227 MI ranking, META-231 Boruta (filter and wrapper alternatives)
- **Coexists with:** META-225 Stability Selection (can run both, intersect results)

## Test Plan
- Perfectly informative features: verify they survive to the last iteration
- Noise-only columns: verify eliminated first
- Step-size=1 vs step=d/10: verify produces same top-k (order may differ inside dropped block)
- Collinear features: verify ridge regularization prevents instability
