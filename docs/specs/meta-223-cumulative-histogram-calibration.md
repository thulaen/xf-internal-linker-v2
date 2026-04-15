# META-223 — Cumulative Histogram Calibration

## Overview
**Category:** Probability calibration
**Extension file:** `cumhist_calibration.cpp`
**Replaces/improves:** Equal-width histogram binning in `calibration.py`
**Expected speedup:** ≥5x over Python histogram + isotone-projection loop
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

Non-decreasing Bayesian histogram calibration with empirical-CDF-spaced bins (Kumar et al. NeurIPS 2019).

```
Input: scores s ∈ [0,1]^n, labels y ∈ {0,1}^n, B bins, Beta prior (α, β)
Output: monotone-increasing calibrator g(s)

1. Sort scores; bin edges at empirical CDF quantiles (equal-mass bins):
     edge_b = s[⌊(b/B)·n⌋]
2. For each bin b, compute Bayesian posterior mean with Beta(α, β) prior:
     P(y=1 | s ∈ bin_b) = (Σ y_i · I(s_i ∈ bin_b) + α) / (Σ I(s_i ∈ bin_b) + α + β)
3. Enforce monotonicity via PAV on bin estimates:
     g(bin_1) ≤ g(bin_2) ≤ … ≤ g(bin_B)
4. Predict via bin-lookup + linear interpolation between bin centres
```

- **Time complexity:** O(n log n) sort + O(B log B) PAV + O(m log B) lookup
- **Space complexity:** O(B) bin edges + counts
- **Convergence:** Closed-form posterior + PAV is exact in one pass

## C++ Interface (pybind11)

```cpp
// Fit cumulative histogram calibrator; predict on query scores
std::vector<float> cumhist_fit_predict(
    const float* scores, const int* labels, int n,
    const float* query_scores, int m,
    int num_bins, float alpha_prior, float beta_prior,
    bool enforce_monotone
);
```

## Memory Budget
- Runtime RAM: <10 MB (bin edges + counts + PAV workspace)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n + num_bins)`

## Performance Target
- Python baseline: NumPy histogram + sklearn isotonic projection
- Target: ≥5x faster (single-pass bin-count + inline PAV)
- Benchmark: n ∈ {1k, 10k, 100k} × B ∈ {10, 30, 100} bins

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Guard empty bins via prior. Double accumulator for bin sums.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_223.py` | Output matches Python reference within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_223.py` | n<B, empty bin, tied edges, NaN pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance + monotonicity check |

## Dependencies
- Shares PAV utility with META-221 (extract to internal header)

## Pipeline Stage & Non-Conflict
- **Stage:** Post-scoring calibration (after ranker, before threshold application)
- **Owns:** Bayesian-posterior histogram calibrator with optional monotonicity
- **Alternative to:** META-219 BBQ, META-220 spline, META-221 Venn-Abers
- **Coexists with:** Reliability diagnostics (META-216), threshold tuning (META-217)

## Test Plan
- Uniform s, random y: verify calibrator converges to base rate
- Heavy class imbalance: verify prior (α, β) prevents empty-bin extremes
- Monotonicity flag off: verify raw bin estimates returned
- ECE improvement: verify held-out ECE drops vs uncalibrated on synthetic skew
