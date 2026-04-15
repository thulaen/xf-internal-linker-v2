# META-225 — Stability Selection

## Overview
**Category:** Feature selection (resampling-based)
**Extension file:** `stability_selection.cpp`
**Replaces/improves:** Single-shot LASSO selection in `feature_engineering.py`
**Expected speedup:** ≥6x over sklearn `StabilitySelection` Python loop
**RAM:** <50 MB | **Disk:** <1 MB

## Algorithm

Run LASSO on B bootstrap subsamples; keep features with selection frequency above threshold (Meinshausen & Bühlmann 2010).

```
Input: X ∈ ℝ^{n×d}, y ∈ ℝ^n, B bootstrap draws, subsample size ⌊n/2⌋, threshold π_thr
Output: stable feature set Ŝ_stable

for b = 1..B:
    I_b ← random subsample of ⌊n/2⌋ indices (without replacement)
    Ŝ(λ, b) ← argmin_β { ‖y_{I_b} − X_{I_b}·β‖² + λ·‖β‖_1 }
    Ŝ(λ, b) ← { j : β_j ≠ 0 }                        (LASSO support)

Selection frequency per feature j:
    π̂_j(λ) = (1/B) · Σ_b I(j ∈ Ŝ(λ, b))

Output:
    Ŝ_stable = { j : π̂_j(λ) ≥ π_thr }                (π_thr typically 0.6-0.9)

Error control (Meinshausen–Bühlmann bound):
    E[#false selections] ≤ q_Λ² / ((2·π_thr − 1) · d)
```

- **Time complexity:** O(B · lasso_fit_cost) — embarrassingly parallel over b
- **Space complexity:** O(B · d) for support indicator matrix
- **Convergence:** Monte-Carlo convergence in B; LASSO fit is convex

## C++ Interface (pybind11)

```cpp
// Run stability selection; return per-feature selection frequencies + stable set
struct StabilityOut { std::vector<float> pi_hat; std::vector<int> stable_set; };

StabilityOut stability_select(
    const float* X, int n, int d,
    const float* y,
    int num_bootstrap, float lasso_lambda,
    float pi_threshold, unsigned seed
);
```

## Memory Budget
- Runtime RAM: <50 MB (B × d support matrix + per-bootstrap workspace)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(num_bootstrap * d)`

## Performance Target
- Python baseline: Python loop over `sklearn.linear_model.Lasso`
- Target: ≥6x faster (parallel bootstraps, warm-start across b)
- Benchmark: n=10k × d ∈ {100, 500, 2000} × B ∈ {50, 100, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** Parallel across bootstrap index `b` — each thread owns its LASSO workspace. No shared mutable state except atomic frequency accumulator. All atomics document memory ordering (`relaxed` for counters, `acq_rel` for final reduction).

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Standardize X columns before LASSO. Double accumulator for residuals.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. Use explicit RNG seed — never `rand()`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_225.py` | π̂ within 1e-3 of Python reference (same seed) |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python reference |
| 5 | `pytest test_edges_meta_225.py` | B=1, d=1, perfectly collinear, all-zero y pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races across bootstrap threads |
| 8 | Human reviewer | CPP-RULES.md compliance + MB error-bound check |

## Dependencies
- LASSO coordinate-descent solver (reuse or vendored minimal implementation)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-training feature selection (before ranker fit)
- **Owns:** Resampling-based stability frequencies π̂
- **Alternative to:** META-224 RFE, META-226 mRMR, META-231 Boruta
- **Coexists with:** Any filter method (META-227/228/229) — intersect stable sets

## Test Plan
- Spike-and-slab synthetic (20 true, 80 noise): verify true features have π̂ > 0.9
- Collinear true features: verify stability still selects at least one
- Threshold sweep: verify π_thr ∈ [0.6, 0.9] monotone reduces stable set size
- Determinism: verify same seed → identical π̂ across runs
