# META-221 — Venn-Abers Predictors

## Overview
**Category:** Probability calibration (interval-valued)
**Extension file:** `venn_abers.cpp`
**Replaces/improves:** Point-estimate isotonic calibration in `calibration.py`
**Expected speedup:** ≥4x over Python isotonic regression pair
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

Inductive Venn-Abers: partition training data by score, emit interval (p₀, p₁) (Vovk & Petej, 2014).

```
Input: calibration scores s ∈ [0,1]^n, labels y ∈ {0,1}^n, query score s*
Output: interval (p₀, p₁) — lower and upper calibrated probability

1. Append (s*, 0) to training set → fit isotonic regression → read f_0(s*) = p₀
2. Append (s*, 1) to training set → fit isotonic regression → read f_1(s*) = p₁
3. Emit interval (p₀, p₁)

Point estimate for ranking:
  p_hat = p₁ / (1 − p₀ + p₁)                        (Vovk's merging formula)
```

- **Time complexity:** O(n log n) per query (two PAV runs sharing sorted order)
- **Space complexity:** O(n) for sorted scores + label counts
- **Convergence:** Closed-form — PAV (Pool-Adjacent-Violators) is exact in one pass

## C++ Interface (pybind11)

```cpp
// Fit Venn-Abers calibrator; return (p0, p1) intervals + merged point estimate
struct VennAbersResult { std::vector<float> p0, p1, p_hat; };

VennAbersResult venn_abers_predict(
    const float* cal_scores, const int* cal_labels, int n,
    const float* query_scores, int m
);
```

## Memory Budget
- Runtime RAM: <15 MB (sorted cal set + two isotonic fits)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n + 1)`

## Performance Target
- Python baseline: `sklearn.isotonic.IsotonicRegression` called twice per query
- Target: ≥4x faster (shared sort, PAV reuse, batched queries)
- Benchmark: n ∈ {1k, 10k, 100k} calibration × m = 1000 queries

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Guard division in merging formula when `1 − p₀ + p₁` → 0.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_221.py` | (p₀,p₁) within 1e-4 of Python reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_221.py` | n=1, tied scores, all-zero labels, NaN pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance + interval validity proof |

## Dependencies
- None (standalone calibrator; reuses internal PAV implementation)

## Pipeline Stage & Non-Conflict
- **Stage:** Post-scoring calibration (after ranker, before threshold application)
- **Owns:** Interval-valued calibrated probability estimates
- **Alternative to:** META-04x Platt, META-219 BBQ, META-220 spline (all emit points not intervals)
- **Coexists with:** Reliability diagram diagnostics (META-216), conformal prediction wrappers

## Test Plan
- Perfectly calibrated input: verify `p₀ ≈ p₁ ≈ s` within 1e-3
- Tied scores at boundary: verify interval is non-empty (p₀ ≤ p₁)
- Validity: verify coverage of `y` by interval ≥ nominal over 10k draws
- Merging formula: verify point estimate lies in [p₀, p₁]
