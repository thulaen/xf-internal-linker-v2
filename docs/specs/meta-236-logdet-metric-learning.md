# META-236 — LogDet Metric Learning

## Overview
**Category:** Distance metric learning — Bregman divergence primitive
**Extension file:** `logdet_metric.cpp`
**Replaces/improves:** KL-style matrix divergences for metric learning
**Expected speedup:** ≥5x over NumPy `scipy.linalg.slogdet` chain
**RAM:** <24 MB | **Disk:** <1 MB

## Algorithm

```
Input: PSD matrices M₁, M₀ ∈ ℝ^{d×d}; pairwise constraints C
Output: Bregman divergence value and updated M₁

LogDet Bregman divergence (paper, eq. 3):
  D_ld(M₁, M₀) = tr(M₁ · M₀⁻¹) − log det(M₁ · M₀⁻¹) − d

Bregman projection onto constraint set (paper, Algorithm 2):
  M ← M₁
  for each pair constraint (x_i, x_j, target t):
    p ← (x_i − x_j)ᵀ · M · (x_i − x_j)
    α ← Lagrange multiplier solving closed form for LogDet
    β ← α / (1 − α·p)
    M ← M + β · M · (x_i − x_j)(x_i − x_j)ᵀ · M
  repeat until all constraints within tol

Closed-form rank-1 update preserves PSD — paper Theorem 1.
```

- **Time complexity:** O(iters · |C| · d²) via rank-1 SYRK updates
- **Space complexity:** O(d²) for M and M₀⁻¹

## Academic Source
Kulis, B., Sustik, M., and Dhillon, I. S. "Low-rank kernel learning with Bregman matrix divergences." Journal of Machine Learning Research 10 (2009), pp. 341–376. Algorithmic content also in Kulis, Sustik, Dhillon at ICML 2009. DOI: 10.5555/1577069.1577079

## C++ Interface (pybind11)

```cpp
// Compute LogDet Bregman divergence between two PSD matrices
double logdet_divergence(
    const float* M1, const float* M0_inv, int d
);

// Apply one pass of Bregman projection to satisfy constraints
void logdet_project(
    float* M, int d,
    const float* X, int n,
    const int* pairs, const float* targets, int n_pairs,
    float tol, int max_iters
);
```

## Memory Budget
- Runtime RAM: <24 MB (M + M₀⁻¹ + Cholesky scratch; d≤256)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d*d)`; `alignas(64)` on matrices

## Performance Target
- Python baseline: `numpy.linalg.slogdet` + manual update
- Target: ≥5x faster via LAPACK `dpotrf` + rank-1 SYR2K
- Benchmark: d=32, 64, 128 with 1k constraints

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on hot matrices.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for trace and log-det. Log arg clamped to `max(·, 1e-300)`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_236.py` | Divergence matches SciPy slogdet within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_236.py` | Identical matrices (div=0), singular M₀, all zero columns handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-218 (LAPACK bindings) for Cholesky + slogdet
- Used by META-235 (ITML) as the core divergence

## Pipeline Stage Non-Conflict
- **Owns:** LogDet Bregman divergence and rank-1 preserving projection
- **Alternative to:** Frobenius, KL-style matrix divergences
- **Coexists with:** META-235 (ITML uses LogDet as its optimisation divergence)

## Test Plan
- D_ld(M, M) = 0: verify self-divergence is zero
- Asymmetry: verify D_ld(M₁, M₀) ≠ D_ld(M₀, M₁) in general
- PSD preservation: verify smallest eigenvalue of M stays ≥ 0 after projection
- Singular M₀: verify raises with a clear error
