# META-206 — Singular Value Decomposition (SVD)

## Overview
**Category:** Matrix factorisation (dense, exact)
**Extension file:** `svd.cpp`
**Replaces/improves:** `numpy.linalg.svd` / `scipy.sparse.linalg.svds` for rank-k truncation on dense embedding matrices
**Expected speedup:** ≥4x over numpy for rank-k (k << min(m,n))
**RAM:** <120 MB for 20k×256 | **Disk:** <1 MB

## Algorithm

```
Input:  A ∈ ℝ^{m×n}, target rank k ≤ min(m,n)
Output: U_k ∈ ℝ^{m×k}, Σ_k ∈ ℝ^{k×k} (diag), V_k ∈ ℝ^{n×k}
Paper formula: A = U·Σ·Vᵀ  ;  A_k = U_k·Σ_k·V_kᵀ

Step 1 — Householder bidiagonalisation:
    A → U₁·B·V₁ᵀ where B is upper bidiagonal
    (apply m-1 left and n-2 right Householder reflectors)

Step 2 — Implicit QR on B:
    repeat until off-diagonals ≤ ε·‖B‖:
        pick Wilkinson shift μ from trailing 2×2
        apply Givens rotations to chase bulge (implicit shift QR)
    → B = U₂·Σ·V₂ᵀ

Step 3 — Combine and truncate:
    U = U₁·U₂,  V = V₁·V₂
    U_k ← first k columns of U
    Σ_k ← top-k singular values (already sorted desc by QR)
    V_k ← first k columns of V
```

- **Time complexity:** O(m·n² + n³) full; O(m·n·k) for rank-k path via randomised variant
- **Space complexity:** O(m·n) workspace for dense A; reflector vectors stored in lower/upper triangle

## Academic Source
Golub, G. H. & Van Loan, C. F. *Matrix Computations* (1st ed., Johns Hopkins University Press, 1983). Chapter 8 (bidiagonalisation), Chapter 8.6 (SVD algorithm). ISBN 0-8018-3010-9. DOI (4th ed.): 10.1353/book.72122.

## C++ Interface (pybind11)

```cpp
// Thin truncated SVD: A (row-major m×n) → (U_k, sigma_k, V_k)
std::tuple<py::array_t<float>, py::array_t<float>, py::array_t<float>>
svd_truncated(
    py::array_t<float, py::array::c_style | py::array::forcecast> A,
    int k,
    float tol = 1e-6f,
    int max_qr_sweeps = 75
);
```

## Memory Budget
- Runtime RAM: <120 MB at m=20000, n=256, k=64 (A + U + V + workspace)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: single `std::vector<float>` per matrix, `reserve(m*n)` up-front, no in-loop allocation

## Performance Target
- Baseline: `numpy.linalg.svd(A, full_matrices=False)` then slice [:k]
- Target: ≥4x for k ≤ 128 on m×256 matrices (avoids computing full U, V)
- Benchmark: 3 sizes — (1000×64, k=16), (5000×128, k=32), (20000×256, k=64)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. All atomics document memory ordering. Reflector application is sequential (no parallel section inside bulge chase).

**Memory:** No raw `new`/`delete`. Arena allocation for reflector workspace. Bounds-checked in debug. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. Return by value, not by reference to local workspace.

**Type safety:** Explicit `static_cast<int>` for narrowing. No signed/unsigned mismatch in index arithmetic.

**SIMD:** AXPY and dot-product kernels use AVX2 with `alignas(64)` rows; `_mm256_zeroupper()` before returning to Python.

**Floating point:** Double accumulator for dot products when m > 1024. NaN/Inf entry check on A. Flush-to-zero on init.

**Performance:** No `std::endl` in loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on non-finite input or k > min(m,n).

**Build:** No cyclic includes. Extension frees own memory (no Python-heap interleave).

**Security:** No `system()`. Scrub workspace on error path.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_206.py` | U·Σ·Vᵀ reconstructs A within 1e-5 vs numpy |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than numpy on all 3 sizes |
| 5 | `pytest test_edges_meta_206.py` | Rank-deficient, k=1, k=min(m,n), NaN/Inf all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone; does not depend on other META extensions)

## Pipeline Stage Non-Conflict
- **Stage owned:** Offline dimensionality reduction of embedding matrix before indexing
- **Owns:** Truncated SVD of dense embedding tables (rank-k)
- **Alternative to:** META-207 (NMF — non-negative constraint), META-210 (WALS — implicit feedback matrices)
- **Coexists with:** META-208 (PMF, which consumes the SVD init as warm-start)

## Test Plan
- Orthogonal test matrix (Uᵀ U = I): verify singular values = 1 exactly (±1e-6)
- Rank-2 Hilbert matrix: verify top-2 σ match reference to 1e-5
- NaN entry: verify raises `py::value_error` with clear message
- k = min(m,n): verify full reconstruction ‖A − U·Σ·Vᵀ‖_F < 1e-5·‖A‖_F
- Random 500×200 rank-20 matrix: verify rank-20 reconstruction error < 1e-6
