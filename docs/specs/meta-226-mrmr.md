# META-226 — mRMR (Minimum Redundancy Maximum Relevance)

## Overview
**Category:** Feature selection (filter, sequential)
**Extension file:** `mrmr.cpp`
**Replaces/improves:** Pure MI-ranking selection in `feature_engineering.py`
**Expected speedup:** ≥7x over Python sequential-selection loop
**RAM:** <40 MB | **Disk:** <1 MB

## Algorithm

Sequentially select features maximising relevance to y while penalising redundancy with already-chosen features (Peng, Long & Ding 2005).

```
Input: feature matrix X ∈ ℝ^{n×d}, labels y, target count k
Output: ordered selected set S of size k

S ← ∅
while |S| < k:
    for each candidate f_i ∈ F \ S:
        relevance_i  = I(f_i; y)
        redundancy_i = (1/|S|) · Σ_{f_j ∈ S} I(f_i; f_j)    (MID variant)
        score_i      = relevance_i − redundancy_i
    f* = argmax_i score_i
    S ← S ∪ {f*}
return S in selection order

Variants:
  MID (difference): score = relevance − redundancy               (above)
  MIQ (quotient):   score = relevance / max(redundancy, ε)
```

- **Time complexity:** O(k · d · n) — one MI eval per (candidate, target or incumbent) pair, cached
- **Space complexity:** O(d²) for MI cache + O(n·d) for discretized features
- **Convergence:** Greedy — monotone non-decreasing relevance, bounded redundancy

## C++ Interface (pybind11)

```cpp
// mRMR greedy selection; returns feature indices in selection order
std::vector<int> mrmr_select(
    const float* X, int n, int d,
    const int* y_discrete, int num_y_classes,
    int target_k, int num_bins_per_feature,
    const char* variant   // "MID" or "MIQ"
);
```

## Memory Budget
- Runtime RAM: <40 MB (discretized X + d×d MI cache)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d * d)`

## Performance Target
- Python baseline: `pymrmr` or Python loop over `sklearn.metrics.mutual_info_score`
- Target: ≥7x faster (MI cache, SIMD contingency-table builds)
- Benchmark: n=10k × d ∈ {100, 500, 2000} × k ∈ {10, 50}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Parallel across candidate features within each iteration; cache writes use `acq_rel` atomics.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for entropy sums. Guard `log(0)` via small ε.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_226.py` | Selected set matches `pymrmr` for same discretization |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥7x faster than Python reference |
| 5 | `pytest test_edges_meta_226.py` | k=d, k=1, constant features, all-identical features pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races in MI cache |
| 8 | Human reviewer | CPP-RULES.md compliance + MI computation audit |

## Dependencies
- MI computation (reuse META-227 kernel via shared header)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-training feature selection (before ranker fit)
- **Owns:** Sequential greedy selection balancing relevance and redundancy
- **Alternative to:** META-224 RFE, META-225 Stability Selection, META-227 MI ranking, META-231 Boruta
- **Coexists with:** χ² (META-228), ANOVA-F (META-229) as parallel filter candidates

## Test Plan
- Synthetic with known redundant pairs: verify mRMR picks one per pair, not both
- Pure-MI baseline comparison: verify mRMR selects fewer redundant features
- MID vs MIQ: verify both return valid but distinct rankings
- k=d: verify all features selected in some order
