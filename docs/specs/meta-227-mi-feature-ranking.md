# META-227 — Mutual Information Feature Ranking

## Overview
**Category:** Feature selection (filter, univariate)
**Extension file:** `mi_ranking.cpp`
**Replaces/improves:** sklearn `mutual_info_classif` Python loop in `feature_engineering.py`
**Expected speedup:** ≥6x over Python reference
**RAM:** <25 MB | **Disk:** <1 MB

## Algorithm

Compute I(f_j; y) for each feature; rank by MI (Battiti 1994).

```
Input: feature matrix X ∈ ℝ^{n×d}, labels y (categorical), bins B per feature
Output: per-feature MI score; ranking

for j = 1..d:
    discretize x_j into B bins (equal-frequency or uniform-width)
    build joint contingency table C[b, c] = |{i : x_ij ∈ bin_b ∧ y_i = c}|
    marginalize:
        p(b)    = (Σ_c C[b, c]) / n
        p(c)    = (Σ_b C[b, c]) / n
        p(b, c) = C[b, c] / n
    I(x_j; y) = Σ_{b, c} p(b, c) · log( p(b, c) / (p(b) · p(c)) )
return argsort(I, descending)

Miller-Madow bias correction (optional):
    I_corrected = I_raw + (|bins| − 1)·(|classes| − 1) / (2·n · ln 2)
```

- **Time complexity:** O(n·d) discretize + O(d·B·C) MI compute
- **Space complexity:** O(d + B·C) per-feature
- **Convergence:** Closed-form — no iteration

## C++ Interface (pybind11)

```cpp
// MI score per feature + sorted indices (descending by MI)
struct MIRankOut { std::vector<float> mi; std::vector<int> ranking; };

MIRankOut mi_feature_ranking(
    const float* X, int n, int d,
    const int* y_discrete, int num_y_classes,
    int num_bins_per_feature,
    bool use_miller_madow_correction
);
```

## Memory Budget
- Runtime RAM: <25 MB (discretized X + per-feature contingency tables)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n * d)`

## Performance Target
- Python baseline: `sklearn.feature_selection.mutual_info_classif`
- Target: ≥6x faster (parallel across features, SIMD histogram builds)
- Benchmark: n ∈ {10k, 100k} × d ∈ {100, 1000, 5000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** Parallel across feature index `j`. Each thread owns its contingency buffer. No shared mutable state in MI-compute inner loop.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on contingency buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for entropy sums. Guard `log(0)` via ε or skip zero cells.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_227.py` | MI within 1e-4 of sklearn for identical discretization |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than sklearn reference |
| 5 | `pytest test_edges_meta_227.py` | n=1, constant feature, all-identical labels, NaN pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races in parallel MI compute |
| 8 | Human reviewer | CPP-RULES.md compliance + MI formula audit |

## Dependencies
- Shared MI kernel with META-226 (extract to internal header)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-training feature selection (before ranker fit)
- **Owns:** Univariate MI score per feature
- **Alternative to:** META-228 χ², META-229 ANOVA-F (univariate filters)
- **Coexists with:** META-226 mRMR (consumes this kernel), META-224 RFE, META-225 Stability Selection

## Test Plan
- Perfectly predictive feature: verify MI = H(y)
- Independent feature: verify MI ≈ 0 (within Miller-Madow correction)
- Constant feature: verify MI = 0 exactly
- Binning sweep: verify MI is non-decreasing with more bins (raw), stable with MM correction
