# META-144 — B-Spline Basis Features

## Overview
**Category:** Feature engineering
**Extension file:** `bspline_basis.cpp`
**Replaces/improves:** Polynomial expansion for monotone/smooth features where B-splines give better local support
**Expected speedup:** ≥4x over scipy `BSpline` design matrix
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

```
Input: column x ∈ ℝ^N, order k, knot vector t with |t| = n+k+1
Output: basis matrix B ∈ ℝ^{N × n} where B[i, j] = B_{j,k}(x_i)

Cox–de Boor recursion (de Boor 1978):
    B_{i,1}(x) = 1  if t_i ≤ x < t_{i+1} else 0
    B_{i,k}(x) = ((x − t_i) / (t_{i+k−1} − t_i))    · B_{i,k−1}(x)
              + ((t_{i+k} − x) / (t_{i+k} − t_{i+1})) · B_{i+1,k−1}(x)
```

- **Time complexity:** O(N · k) per column using local-support evaluation (only k basis functions non-zero per x)
- **Space complexity:** O(N · n) for dense basis; O(N · k) with sparse/packed storage
- **Convergence:** Partition of unity (Σ_j B_{j,k}(x) = 1) preserved

## C++ Interface (pybind11)

```cpp
// Dense B-spline basis matrix
void bspline_basis(
    float* B_out,                       // (N, n_basis)
    const float* x, int N,
    const float* knots, int num_knots,  // n + k + 1
    int order                           // k (e.g. 4 = cubic)
);

int bspline_num_basis(int num_knots, int order);  // = num_knots - order
```

## Memory Budget
- Runtime RAM: <30 MB (dense output)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned output

## Performance Target
- Python baseline: scipy `BSpline.design_matrix`
- Target: ≥4x faster via local Cox–de Boor kernel
- Benchmark: N=10000, (order, n_basis) ∈ {(4, 16), (4, 64), (6, 64)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Knots must be non-decreasing — validate.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Coincident knots: denominator guard using epsilon shift; treat 0/0 in recursion as 0.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_144.py` | Output matches scipy BSpline within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than scipy |
| 5 | `pytest test_edges_meta_144.py` | x at knot, coincident knots, x outside support all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** B-spline design matrix for 1D numerical columns
- **Alternative to:** META-143 (polynomial), META-145 (natural cubic), META-146 (Fourier RFF) — mutually exclusive per column
- **Coexists with:** META-147..150 categorical encoders; optimizers META-128..135

## Test Plan
- Partition of unity: each row of B sums to 1 within 1e-6 (when x in interior)
- x at knot boundary: matches scipy to 1e-5
- Coincident knots (multiplicity): stable
- Empty input N=0: returns (0, n_basis) shape
