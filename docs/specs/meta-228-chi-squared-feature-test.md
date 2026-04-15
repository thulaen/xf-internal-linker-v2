# META-228 — χ² Feature Test

## Overview
**Category:** Feature selection (filter, univariate, categorical)
**Extension file:** `chi_squared.cpp`
**Replaces/improves:** sklearn `chi2` Python loop in `feature_engineering.py`
**Expected speedup:** ≥8x over Python/SciPy reference
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

Compute Pearson's χ² independence statistic per (categorical feature, categorical target) pair; rank by p-value (Liu & Setiono 1995).

```
Input: feature matrix X ∈ {0..K_f−1}^{n×d}, labels y ∈ {0..C−1}^n
Output: per-feature χ² statistic, degrees of freedom, p-value, ranking

for j = 1..d:
    build observed counts O[a, c] = |{i : x_ij = a ∧ y_i = c}|
    marginals:
        R[a] = Σ_c O[a, c]
        N[c] = Σ_a O[a, c]
        n    = Σ_a R[a]
    expected counts under independence:
        E[a, c] = R[a] · N[c] / n
    χ²_j = Σ_{a, c} (O[a, c] − E[a, c])² / max(E[a, c], ε)
    df_j  = (K_f − 1) · (C − 1)
    p_j   = 1 − CDF_{χ²_{df_j}}(χ²_j)
return argsort(p, ascending)   // smallest p-value = most informative
```

- **Time complexity:** O(n·d + d·K_f·C)
- **Space complexity:** O(d + K_f·C) per-feature
- **Convergence:** Closed-form — no iteration

## C++ Interface (pybind11)

```cpp
// χ² statistic + p-value per feature; ranking by ascending p-value
struct ChiSqOut {
    std::vector<float> chi2; std::vector<int> df;
    std::vector<float> p_value; std::vector<int> ranking;
};

ChiSqOut chi_squared_ranking(
    const int* X, int n, int d, const int* feature_cardinalities,
    const int* y, int num_y_classes,
    float min_expected_count   // combine cells if E < this threshold
);
```

## Memory Budget
- Runtime RAM: <15 MB (per-feature contingency + chi2/p arrays)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d * K_f_max * C)`

## Performance Target
- Python baseline: `sklearn.feature_selection.chi2` + `scipy.stats.chi2.cdf`
- Target: ≥8x faster (parallel features, inline χ² survival via series expansion)
- Benchmark: n ∈ {10k, 100k} × d ∈ {100, 1000, 5000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** Parallel across feature index `j`. Each thread owns its contingency buffer.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on contingency buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for χ² sums. Guard E[a,c]=0 via min_expected_count merging.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Use `std::lgamma` for χ² survival approximation.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_228.py` | χ² and p within 1e-4 of scipy reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than sklearn/scipy reference |
| 5 | `pytest test_edges_meta_228.py` | Sparse cells, 2x2 table, empty column, NaN pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races in parallel compute |
| 8 | Human reviewer | CPP-RULES.md compliance + statistical validity audit |

## Dependencies
- χ² survival function (series expansion, vendored in internal header)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-training feature selection (before ranker fit) — categorical features only
- **Owns:** χ² independence test statistic + p-value
- **Alternative to:** META-227 MI (continuous/discrete), META-229 ANOVA-F (numeric features)
- **Coexists with:** META-226 mRMR (can be combined as pre-filter), META-225 Stability Selection

## Test Plan
- Independent synthetic: verify p-value ≈ uniform on [0,1] across many draws
- Perfectly dependent feature: verify p ≈ 0 and χ² large
- Sparse 2x2 table: verify Yates correction flag behaves correctly
- Cell merging: verify min_expected_count merging preserves total count
