# META-143 — Polynomial Feature Expansion

## Overview
**Category:** Feature engineering
**Extension file:** `poly_features.cpp`
**Replaces/improves:** scikit-learn `PolynomialFeatures` for ranker feature preprocessing
**Expected speedup:** ≥5x over sklearn `PolynomialFeatures`
**RAM:** <50 MB | **Disk:** <1 MB

## Algorithm

```
Input: feature matrix X ∈ ℝ^{N×d}, degree p, include_bias
Output: expanded Φ(X) ∈ ℝ^{N × C(d+p, p)}

Rule (Fukunaga, 1990):
    for each sample x = (x₁, ..., x_d):
        enumerate all multi-indices α = (α₁,...,α_d) with |α| ≤ p
        feature_α = ∏_j x_j^{α_j}
    output dimension: C(d+p, p) = (d+p)! / (p! · d!)
```

- **Time complexity:** O(N · C(d+p, p))
- **Space complexity:** O(N · C(d+p, p)) for output; O(C(d+p, p)) for multi-index table
- **Convergence:** Injective map on the algebra of polynomial functions of degree ≤ p

## C++ Interface (pybind11)

```cpp
// Polynomial feature expansion up to given degree
void polynomial_features(
    float* phi_out,                   // (N, out_dim)
    const float* X, int N, int d,
    int degree, bool include_bias
);

int polynomial_feature_count(int d, int degree, bool include_bias);
```

## Memory Budget
- Runtime RAM: <50 MB (output tensor) — caller sizes based on polynomial_feature_count
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned output

## Performance Target
- Python baseline: scikit-learn `PolynomialFeatures`
- Target: ≥5x faster via precomputed multi-index table + AVX2 row expansion
- Benchmark: N=10000, (d, p) ∈ {(8, 3), (16, 3), (32, 2)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Degree ≥ 1 enforced; guard C(d+p,p) overflow for large d,p.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Use log-product if any |x_j| > 1e3 and p ≥ 3 to avoid overflow.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_143.py` | Output matches sklearn PolynomialFeatures within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than sklearn |
| 5 | `pytest test_edges_meta_143.py` | p=1 (identity+bias), d=1, include_bias=false all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Polynomial-basis expansion of numerical features
- **Alternative to:** META-144 (B-spline), META-145 (natural cubic), META-146 (Fourier RFF) — mutually exclusive per feature column bundle
- **Coexists with:** META-147..150 categorical encoders; any downstream optimizer META-128..135

## Test Plan
- p=1, include_bias=true: output is [1, x₁, ..., x_d] identically
- Multi-index count matches C(d+p, p) exactly
- Reproducible across runs
- NaN input: raises ValueError
