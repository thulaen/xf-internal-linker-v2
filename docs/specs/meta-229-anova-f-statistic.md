# META-229 — ANOVA F-statistic Feature Ranking

## Overview
**Category:** Feature selection (filter, univariate, numeric feature × categorical target)
**Extension file:** `anova_f.cpp`
**Replaces/improves:** sklearn `f_classif` Python loop in `feature_engineering.py`
**Expected speedup:** ≥8x over Python/SciPy reference
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

One-way ANOVA F-statistic per (numeric feature, categorical target) (Fisher 1918).

```
Input: feature matrix X ∈ ℝ^{n×d}, labels y ∈ {0..k−1}^n
Output: per-feature F statistic + p-value, ranking by p ascending

For each feature j:
    overall mean:  x̄   = (1/n) · Σ_i x_ij
    group means:   x̄_g = (1/n_g) · Σ_{i∈g} x_ij           for g = 1..k
    between-group SS:
        SS_between = Σ_g  n_g · (x̄_g − x̄)²
    within-group SS:
        SS_within  = Σ_g  Σ_{i∈g} (x_ij − x̄_g)²
    F_j = (SS_between / (k − 1)) / (SS_within / (n − k))
    df1 = k − 1,  df2 = n − k
    p_j = 1 − CDF_{F(df1, df2)}(F_j)
return argsort(p, ascending)
```

- **Time complexity:** O(n·d) — single pass per feature
- **Space complexity:** O(d + k) per-feature group sums
- **Convergence:** Closed-form — no iteration

## C++ Interface (pybind11)

```cpp
// ANOVA F statistic + p-value per feature
struct AnovaOut {
    std::vector<float> f_stat; std::vector<float> p_value;
    std::vector<int> ranking;
};

AnovaOut anova_f_ranking(
    const float* X, int n, int d,
    const int* y, int num_y_classes
);
```

## Memory Budget
- Runtime RAM: <10 MB (per-thread group sums + output arrays)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d + num_y_classes)`

## Performance Target
- Python baseline: `sklearn.feature_selection.f_classif` + `scipy.stats.f.sf`
- Target: ≥8x faster (parallel features, fused single-pass Welford sums, incomplete-beta for F survival)
- Benchmark: n ∈ {10k, 100k} × d ∈ {100, 1000, 5000} × k ∈ {2, 10}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** Parallel across feature index `j`. Each thread owns its per-group sum buffer.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Use Welford/two-pass for variance (avoid catastrophic cancellation). Double accumulator for SS.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Use regularized incomplete beta for F-distribution survival.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_229.py` | F and p within 1e-4 of scipy reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than sklearn/scipy reference |
| 5 | `pytest test_edges_meta_229.py` | n_g=1 (singleton group), SS_within=0, NaN, constant feature pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races in parallel compute |
| 8 | Human reviewer | CPP-RULES.md compliance + ANOVA formula audit |

## Dependencies
- Regularized incomplete beta function (vendored in internal header)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-training feature selection (before ranker fit) — numeric features only
- **Owns:** ANOVA F-statistic and p-value per feature
- **Alternative to:** META-227 MI (works for any feature type), META-228 χ² (categorical only)
- **Coexists with:** META-226 mRMR (as pre-filter), META-225 Stability Selection

## Test Plan
- Perfectly separable groups (e.g. feature = y): verify F very large, p ≈ 0
- Random feature: verify p-value distribution ≈ uniform under null
- SS_within=0 (all values identical within group): verify returns F=∞ safely, p=0
- NaN feature: verify raises `ValueError` before compute (no silent NaN propagation)
