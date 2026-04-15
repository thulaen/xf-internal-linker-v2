# META-249 — Online SVD (Brand's Method)

## Overview
**Category:** Online decomposition (rank-1 update)
**Extension file:** `online_svd_brand.cpp`
**Replaces/improves:** Re-SVD from scratch when a single new column/row arrives
**Expected speedup:** ≥12x over recomputing `numpy.linalg.svd` after each update
**RAM:** <64 MB | **Disk:** <1 MB

## Algorithm

```
Input: current thin SVD A = U · Σ · Vᵀ (U ∈ ℝ^{m×r}, Σ ∈ ℝ^{r×r}, V ∈ ℝ^{n×r})
       update pair (u_new ∈ ℝ^m, v_new ∈ ℝ^n), rank budget k
Output: updated thin SVD of A + u_new · v_newᵀ (or appended column)

Brand rank-1 update (paper, Sections 2–3):
  m = Uᵀ · u_new                     # in-subspace component of u_new
  p = u_new − U · m                   # residual orthogonal to U
  Ra = ‖p‖,   P = p / Ra (if Ra > ε else P = 0)

  n_hat = Vᵀ · v_new                  # same for v_new
  q = v_new − V · n_hat
  Rb = ‖q‖,   Q = q / Rb

  Build (r+1) × (r+1) core matrix:
    K = [ Σ   0 ]   +   [ m  ] · [ n_hat  Rb ]
        [ 0   0 ]       [ Ra ]

  Thin SVD of K:  K = U_K · Σ_K · V_Kᵀ

  Update (paper, eq. 6):
    U ← [ U  P ] · U_K
    Σ ← Σ_K
    V ← [ V  Q ] · V_K

  Truncate to top-k: drop smallest singular value and its columns.
```

- **Time complexity:** O((r+1)³ + m·r + n·r) per update (tiny SVD on (r+1)² core)
- **Space complexity:** O(m·k + n·k + k²)

## Academic Source
Brand, M. "Fast low-rank modifications of the thin singular value decomposition." Linear Algebra and Its Applications 415, no. 1 (2006), pp. 20–30. DOI: 10.1016/j.laa.2005.07.021

## C++ Interface (pybind11)

```cpp
struct BrandSVDState {
    std::vector<float> U;        // m × k
    std::vector<float> V;        // n × k
    std::vector<float> sigma;    // k
    int m_rows, n_cols, k;
};
BrandSVDState brand_init_from_svd(const float* U0, const float* s0,
                                  const float* V0, int m, int n, int k);
void brand_update_rank1(BrandSVDState& s,
                        const float* u_new, const float* v_new);
void brand_append_column(BrandSVDState& s, const float* col_new);
```

## Memory Budget
- Runtime RAM: <64 MB (U, V, small core; m, n ≤ 10k; k ≤ 256)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(m*k + n*k)`; `alignas(64)` on U, V

## Performance Target
- Python baseline: `numpy.linalg.svd` on full rebuilt matrix
- Target: ≥12x faster per update
- Benchmark: m=n=1k, 5k, 10k with k=64; measure per-update latency

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** Core SVD on (r+1)² matrix is sequential. BLAS matmuls can multi-thread. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling refs.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on U, V.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Residual norm guard `Ra > 1e-10` before dividing. Orthogonality periodically re-imposed via QR (every 100 updates).

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Singular K matrix handled by falling back to full SVD.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

Full reference: `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_249.py` | After 100 updates, reconstruction error vs `numpy.svd` rebuild < 1e-3 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥12x faster than full-rebuild baseline |
| 5 | `pytest test_edges_meta_249.py` | Zero-norm residual, append column, rank overflow all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Depends on META-218 (LAPACK bindings) for tiny SVD and periodic QR
- Co-exists with META-248 Incremental PCA

## Pipeline Stage Non-Conflict
- **Owns:** strict rank-1 update to a thin SVD with residual expansion
- **Alternative to:** META-248 batch incremental PCA (which takes m rows at a time)
- **Coexists with:** META-248 (different update cadence — one row/col vs a batch)

## Test Plan
- Compare to full SVD after 10, 100, 1000 updates: verify error < 1e-3
- Zero-norm residual (update lies fully in current subspace): verify K matrix stays (r×r), no expansion
- Rank overflow (r+1 > k): verify truncates correctly and preserves top-k
- Appending many correlated columns: verify singular values plateau (do not explode)
