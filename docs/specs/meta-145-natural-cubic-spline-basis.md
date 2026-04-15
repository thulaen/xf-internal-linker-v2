# META-145 — Natural Cubic Spline Basis

## Overview
**Category:** Feature engineering
**Extension file:** `ncs_basis.cpp`
**Replaces/improves:** Plain B-splines where tail behaviour should be linear (no boundary ringing)
**Expected speedup:** ≥4x over patsy / R `ns()` equivalent
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

```
Input: x ∈ ℝ^N, K interior knots ξ_1 < ξ_2 < ... < ξ_K
Output: basis matrix H ∈ ℝ^{N × K}

Rule (Green & Silverman, 1993):
    cubic polynomial between consecutive knots
    linear in the two tails  (x ≤ ξ_1, x ≥ ξ_K)
    second derivatives continuous at every knot
    second derivative = 0 at the two boundary knots        (the "natural" condition)

Canonical basis (truncated-power form):
    d_k(x) = ((x − ξ_k)_+^3 − (x − ξ_K)_+^3) / (ξ_K − ξ_k)
    H[·, 1] = x
    H[·, k+1] = d_k(x) − d_{K−1}(x)     for k = 1..K−2
```

- **Time complexity:** O(N · K)
- **Space complexity:** O(N · K) dense
- **Convergence:** Interpolates the minimum-curvature smoother through K knots

## C++ Interface (pybind11)

```cpp
// Natural cubic spline basis (K-1 columns, not including intercept)
void natural_cubic_basis(
    float* H_out,                  // (N, K-1)
    const float* x, int N,
    const float* knots, int K
);
```

## Memory Budget
- Runtime RAM: <30 MB (output)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: patsy `dmatrix("cr(x, df=K)")`
- Target: ≥4x faster via closed-form truncated-power kernel
- Benchmark: N=10000, K ∈ {5, 10, 20}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Knots must be strictly increasing — validate.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Guard (ξ_K − ξ_k) denominator against zero (strict-increase assertion).

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_145.py` | Output matches patsy `cr()` design matrix within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than patsy |
| 5 | `pytest test_edges_meta_145.py` | x = ξ_k exactly, x in tails, K=2 (linear only) all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Natural cubic spline basis for 1D columns
- **Alternative to:** META-143 (polynomial), META-144 (B-spline), META-146 (Fourier RFF) — mutually exclusive per column
- **Coexists with:** META-147..150 categorical encoders; optimizers META-128..135

## Test Plan
- Linear tails: verify second derivative ≈ 0 for x outside [ξ_1, ξ_K] within 1e-5
- Continuity: second derivatives match across knot boundaries within 1e-5
- K=2: basis reduces to a single linear column
- Ascending knot validation: non-monotone knots raise ValueError
