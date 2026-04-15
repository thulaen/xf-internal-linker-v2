# META-163 — Kraskov Mutual Information Estimator

## Overview
**Category:** Information-theoretic feature selector
**Extension file:** `kraskov_mi.cpp`
**Replaces/improves:** Binned/histogram MI in `feature_selection.py` and `sklearn.feature_selection.mutual_info_regression` Python loop
**Expected speedup:** ≥8x over Python k-NN MI for N=10k samples
**RAM:** <50 MB | **Disk:** <1 MB

## Algorithm

```
Input: joint samples {(x_i, y_i)}_{i=1..N}, neighbor count k
Output: estimated I(X;Y) in nats

for i = 1..N:
    ε_i/2 ← distance to k-th NN of (x_i, y_i) in joint space (Chebyshev)
    n_x(i) ← |{j : ||x_j - x_i||_∞ < ε_i/2}|
    n_y(i) ← |{j : ||y_j - y_i||_∞ < ε_i/2}|

Î(X;Y) = ψ(k) − ⟨ψ(n_x+1) + ψ(n_y+1)⟩ + ψ(N)
```

- **Time complexity:** O(N log N) using k-d tree
- **Space complexity:** O(N·d) for samples
- **Convergence:** Asymptotically unbiased as N → ∞; low-bias at finite N vs. histogram estimators

## Academic Source
Kraskov A., Stögbauer H., Grassberger P., "Estimating mutual information," *Physical Review E* 69(6):066138, 2004. DOI: 10.1103/PhysRevE.69.066138

## C++ Interface (pybind11)

```cpp
// Kraskov MI estimator (algorithm 1) in nats
double kraskov_mi(
    const float* X, int N, int dx,
    const float* Y, int dy,
    int k
);
```

## Memory Budget
- Runtime RAM: <50 MB (k-d tree + digamma LUT for N=10k)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: arena-backed k-d tree nodes, no per-query `new`

## Performance Target
- Python baseline: `sklearn.feature_selection.mutual_info_regression` k-NN loop
- Target: ≥8x faster for N=10k, d=8
- Benchmark: N ∈ {1k, 10k, 100k}, k=3

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Digamma via Boost or cached LUT; protect ψ(0).

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_163.py` | Matches sklearn `mutual_info_regression` within 5% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than Python reference |
| 5 | `pytest test_edges_meta_163.py` | N<k, duplicates, NaN, N=100k all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- k-d tree primitive (shared with META-170/171/172)

## Pipeline Stage Non-Conflict
- **Owns:** Information-theoretic pairwise dependence I(X;Y) between a feature and the target.
- **Alternative to:** Pearson/Spearman correlation scorers.
- **Coexists with:** META-164 (uses MI as building block), AIC/BIC scorers downstream.
- No conflict with ranking: runs only in the offline feature-selection stage.

## Test Plan
- Independent Gaussians (2D): Î ≈ 0 ± 0.02
- Correlated Gaussians ρ=0.8: Î ≈ −½·log(1−ρ²) within 5%
- Discrete-dressed continuous: verify finite, non-negative
- Duplicate points: verify no ψ(0) crash
- N=100k: verify ≤2s runtime on 4-core CPU
