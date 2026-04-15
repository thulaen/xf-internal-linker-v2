# META-220 — Spline Calibration

## Overview
**Category:** Probability calibration
**Extension file:** `spline_calibration.cpp`
**Replaces/improves:** Piecewise-linear or isotonic calibration in `calibration.py`
**Expected speedup:** ≥5x over Python cvxpy QP solve
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

Monotone natural cubic spline fit via constrained least-squares (Gupta et al. 2021).

```
Input: scores s ∈ [0,1]^n, binary labels y ∈ {0,1}^n, knots K, smoothing λ
Output: calibrator f : [0,1] → [0,1], monotone non-decreasing

Fit:
  min_f  Σ (y_i − f(s_i))²  +  λ · ∫ f''(s)² ds
  s.t.   f(s) = Σ_k β_k · N_k(s)                  (natural cubic B-spline basis)
         f'(s) ≥ 0  ∀ s                            (monotone non-decreasing)
         f(0) ≥ 0, f(1) ≤ 1                        (probability range)

Solve as QP:
  min_β  ‖y − N·β‖²  +  λ · βᵀ·Ω·β
  s.t.   D·β ≥ 0                                   (linearized monotonicity at dense grid)
```

- **Time complexity:** O(n·K + K³) — normal equations + QP on K knots
- **Space complexity:** O(n·K + K²) for design matrix and penalty
- **Convergence:** QP is convex — guaranteed unique global minimum

## C++ Interface (pybind11)

```cpp
// Fit monotone natural cubic spline calibrator; predict on query scores
std::vector<float> spline_calibrate(
    const float* scores, const int* labels, int n,
    const float* query_scores, int m,
    int num_knots, float smoothing_lambda,
    int monotonicity_grid_size
);
```

## Memory Budget
- Runtime RAM: <10 MB (design matrix n×K, QP workspace)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n * num_knots)`

## Performance Target
- Python baseline: `cvxpy` or `scipy.optimize.minimize` with monotone constraint
- Target: ≥5x faster (direct banded Cholesky on B-spline normal equations)
- Benchmark: n ∈ {1k, 10k, 100k} with K=10 knots

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for QP residuals. Regularize ill-conditioned normal equations with λ·I.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_220.py` | Output matches sklearn spline within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_220.py` | n<K, all-zero labels, NaN scores, constant scores pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance + monotonicity proof confirmed |

## Dependencies
- Eigen or small banded-solver header (header-only, vendored)

## Pipeline Stage & Non-Conflict
- **Stage:** Post-scoring calibration (after ranker, before threshold application)
- **Owns:** Smooth monotone calibration curve
- **Alternative to:** META-219 BBQ, isotonic regression, Platt scaling
- **Coexists with:** Reliability diagram diagnostics (META-216), threshold tuning (META-217)

## Test Plan
- Identity input (y=s): verify fitted spline ≈ identity within 1e-3
- Inverted input: verify monotone constraint forces flat fit, not decreasing
- Constant scores: verify returns base rate
- Synthetic miscalibration: verify reliability diagram flattens post-fit
