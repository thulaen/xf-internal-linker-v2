# META-232 — Mahalanobis Metric

## Overview
**Category:** Distance metric learning
**Extension file:** `mahalanobis_metric.cpp`
**Replaces/improves:** Plain Euclidean distance in candidate similarity scoring
**Expected speedup:** ≥6x over NumPy `scipy.spatial.distance.mahalanobis` per-pair call
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm

```
Input: samples X ∈ ℝ^{n×d}, similarity set S, dissimilarity set D
Output: PSD matrix M ∈ ℝ^{d×d} and distance function d_M

Distance:
  d_M(x, y) = √((x − y)ᵀ · M · (x − y))

Learn M ≽ 0 from constraints:
  for (x_i, x_j) ∈ S:  d_M(x_i, x_j) ≤ u     (similar)
  for (x_i, x_j) ∈ D:  d_M(x_i, x_j) ≥ l     (dissimilar)

Closed form (no constraints): M = Σ⁻¹ (inverse sample covariance)
Constrained: semidefinite projection via eigenvalue clipping (λ_i ← max(λ_i, 0))
```

- **Time complexity:** O(n·d² + d³) for covariance + inverse
- **Space complexity:** O(d²) for M plus O(n·d) for X

## Academic Source
Mahalanobis, P. C. "On the generalised distance in statistics." Proceedings of the National Institute of Sciences of India, vol. 2, no. 1, 1936, pp. 49–55.

## C++ Interface (pybind11)

```cpp
// Compute or apply Mahalanobis distance given a learned PSD matrix M
std::vector<float> mahalanobis_pairwise(
    const float* X, int n, int d,
    const float* M_inv_chol, int d_chol,
    bool squared
);
void mahalanobis_fit_covariance(const float* X, int n, int d, float* M_out);
```

## Memory Budget
- Runtime RAM: <12 MB (M matrix for d≤512 plus n×d sample buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*d)`; `alignas(64)` on M

## Performance Target
- Python baseline: `scipy.spatial.distance.mahalanobis` in a loop
- Target: ≥6x faster via batched BLAS gemv
- Benchmark: 1k, 10k, 100k pairs × d=64

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Eigenvalue clipping clamps at 1e-8 to avoid singular inverse.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_232.py` | Output matches scipy.mahalanobis within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python reference |
| 5 | `pytest test_edges_meta_232.py` | Singular M, zero variance, NaN input all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-218 (LAPACK bindings) for Cholesky/eigendecomposition
- Co-exists with META-05 (cosine similarity) — Mahalanobis is an alternate distance

## Pipeline Stage Non-Conflict
- **Owns:** Mahalanobis quadratic form and PSD projection
- **Alternative to:** META-05 cosine sim, plain L2 distance
- **Coexists with:** META-233 LMNN (LMNN learns L = √M; Mahalanobis is the form with a pre-given M)

## Test Plan
- Identity M: verify reduces to Euclidean distance within 1e-6
- Sample covariance: verify matches `numpy.cov` pseudo-inverse
- Singular covariance: verify falls back to pseudo-inverse with warning
- NaN input: verify raises ValueError
