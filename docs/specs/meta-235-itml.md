# META-235 — Information-Theoretic Metric Learning (ITML)

## Overview
**Category:** Distance metric learning
**Extension file:** `itml.cpp`
**Replaces/improves:** LMNN / NCA when only pairwise similarity labels are available (not class labels)
**Expected speedup:** ≥6x over `metric-learn` Python ITML per projection sweep
**RAM:** <32 MB | **Disk:** <1 MB

## Algorithm

```
Input: similarity pairs S, dissimilarity pairs D, prior M₀, bounds u, l
Output: Mahalanobis matrix M ≽ 0

Objective (paper, eq. 3):
  minimise  D_ld(M, M₀)
  subject to
    d_M(x_i, x_j) ≤ u     for (i,j) ∈ S
    d_M(x_i, x_j) ≥ l     for (i,j) ∈ D
    M ≽ 0

D_ld is the LogDet Bregman divergence (see META-236).

Bregman projection algorithm (paper, Algorithm 1):
  M ← M₀
  repeat:
    for each constraint c on pair (i, j):
      p ← (x_i − x_j)ᵀ · M · (x_i − x_j)
      δ_c ← sign(upper? -1 : +1)
      α ← min(λ_c, (1/2)·δ_c·(1/p − γ/ξ_c))
      β ← δ_c·α / (1 − δ_c·α·p)
      M ← M + β · M · (x_i − x_j)(x_i − x_j)ᵀ · M
      ξ_c ← γ·ξ_c / (γ + δ_c·α·ξ_c)
  until constraint violation < tol
```

- **Time complexity:** O(iters · |S ∪ D| · d²)
- **Space complexity:** O(d²) for M

## Academic Source
Davis, J. V., Kulis, B., Jain, P., Sra, S., and Dhillon, I. S. "Information-theoretic metric learning." Proceedings of the 24th International Conference on Machine Learning (ICML 2007), pp. 209–216. DOI: 10.1145/1273496.1273523

## C++ Interface (pybind11)

```cpp
// Learn ITML Mahalanobis matrix from pairwise constraints
std::vector<float> itml_fit(
    const float* X, int n, int d,
    const int* sim_pairs, int n_sim,
    const int* dis_pairs, int n_dis,
    const float* M0, float u, float l,
    float gamma, int max_iters, float tol
);
```

## Memory Budget
- Runtime RAM: <32 MB (M matrix plus constraint buffer; d≤256)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d*d)`; `alignas(64)` on M

## Performance Target
- Python baseline: `metric_learn.ITML`
- Target: ≥6x faster via rank-1 update with symmetric BLAS
- Benchmark: 1k, 10k, 50k pair constraints × d=64

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on M.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for quadratic form p. Divisor clamp `max(ξ, 1e-12)` to avoid division by zero.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_235.py` | Output matches metric-learn ITML within 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python reference |
| 5 | `pytest test_edges_meta_235.py` | No constraints, conflicting constraints, M₀ = 0 all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-236 (LogDet Bregman divergence computation)
- Co-exists with META-232 Mahalanobis form

## Pipeline Stage Non-Conflict
- **Owns:** LogDet-constrained Bregman projection
- **Alternative to:** META-233 LMNN, META-234 NCA
- **Coexists with:** META-236 (LogDet is the divergence; ITML is the constrained optimiser)

## Test Plan
- No constraints: verify returns M₀ unchanged
- Only similarity constraints: verify M shrinks similar pairs
- Conflicting pair (same pair in S and D): verify raises ValueError
- M₀ = I: verify behaves as information-theoretic distance
