# META-210 — Weighted ALS for Implicit Feedback (WALS)

## Overview
**Category:** Matrix factorisation (implicit feedback, alternating least squares)
**Extension file:** `wals_implicit.cpp`
**Replaces/improves:** `implicit` library's ALS solver for click / dwell-based link-engagement matrices
**Expected speedup:** ≥5x over `implicit` at k ≤ 64 (no GPU path for this repo)
**RAM:** <250 MB for 100k × 50k observed matrix, k=32 | **Disk:** <1 MB

## Algorithm

```
Input: observed counts r_ij ≥ 0 for (i,j) ∈ Ω ; rank k ; α (confidence), λ (reg)
Paper constructs (Hu, Koren, Volinsky, ICDM 2008, Eq. 2–3):
  p_ij = 1  if r_ij > 0  else  0           (preference)
  c_ij = 1 + α · r_ij                       (confidence)

Alternating solve (paper Eq. 4–5):
  u_i = (Vᵀ C^i V + λI)⁻¹ · Vᵀ C^i · p_i      for each user i
  v_j = (Uᵀ C^j U + λI)⁻¹ · Uᵀ C^j · p_j      for each item j

Efficient trick (paper §4): for user i
  Vᵀ C^i V  =  VᵀV  +  Vᵀ (C^i − I) V          (precompute VᵀV once per sweep)
  Vᵀ C^i p_i =  Σ_{j: r_ij > 0}  c_ij · V_j

Repeat sweeps until ‖U_new − U_old‖_F / ‖U_old‖_F < tol.
```

- **Time complexity:** O(sweeps · (k³(N+M) + k² · nnz))
- **Space complexity:** O((N+M)·k + k²)
- **Convergence:** Monotone non-increasing of weighted-squared-error objective

## Academic Source
Hu, Y., Koren, Y. & Volinsky, C. "Collaborative Filtering for Implicit Feedback Datasets." *Proceedings of the 8th IEEE International Conference on Data Mining (ICDM 2008)*, 263–272. DOI: 10.1109/ICDM.2008.22.

## C++ Interface (pybind11)

```cpp
// Weighted ALS for implicit feedback; returns user / item factor matrices
std::tuple<py::array_t<float>, py::array_t<float>>
wals_implicit_fit(
    py::array_t<int32_t> row_idx,      // length nnz
    py::array_t<int32_t> col_idx,      // length nnz
    py::array_t<float>   values,       // length nnz  (r_ij > 0)
    int N, int M, int k,
    int sweeps = 15,
    float alpha = 40.0f, float reg = 0.01f,
    float tol = 1e-4f,
    uint64_t seed = 0
);
```

## Memory Budget
- Runtime RAM: <250 MB at N=100000, M=50000, k=32 (U + V + VᵀV + per-thread YtY scratch)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: `reserve((N+M)*k)` + `reserve(k*k)` once; no per-sweep allocation

## Performance Target
- Baseline: `implicit.als.AlternatingLeastSquares(use_gpu=False)`
- Target: ≥5x faster at k=32, |Ω|=1M
- Benchmark: 3 sizes — (1k×1k, |Ω|=20k, k=8), (10k×5k, |Ω|=200k, k=16), (100k×50k, |Ω|=1M, k=32)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** OpenMP parallel across users in u-step; across items in v-step. Precomputed VᵀV read-only. No `volatile`. Document memory ordering.

**Memory:** No raw `new`/`delete`. Arena for per-thread Cholesky scratch (k·k floats). Bounds-checked indices in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for nnz loops.

**SIMD:** AVX2 FMA on V_j V_jᵀ outer product; `_mm256_zeroupper()` before return. `alignas(64)` rows.

**Floating point:** Double accumulator for YtY and confidence sums. Cholesky with jitter ε·I fallback. NaN/Inf on values → `py::value_error`.

**Performance:** No `std::endl`. No `std::function` hot loop. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise on negative r_ij.

**Build:** No cyclic includes. Anonymous namespace for Cholesky helpers.

**Security:** No `system()`. No TOCTOU on seed source.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_210.py` | Recall@10 within 1% of `implicit` library at matched seed |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than `implicit` at all 3 sizes |
| 5 | `pytest test_edges_meta_210.py` | Empty Ω, single-user, negative r_ij rejection pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone; optional warm-start from META-206 SVD)

## Pipeline Stage Non-Conflict
- **Stage owned:** Offline learning of user/item factors from implicit click/dwell counts
- **Owns:** ALS solver with confidence-weighted objective
- **Alternative to:** META-208 (PMF — explicit ratings), META-207 (NMF — non-negative factors)
- **Coexists with:** META-206 (SVD warm-start for U, V initialisation)

## Test Plan
- Synthetic dataset with 5 user-types × 5 item-clusters: verify Recall@5 > 0.9 after 15 sweeps
- All-zero row: verify recovered u_i has near-zero norm (reg dominates)
- Negative r_ij: verify raises `py::value_error`
- Convergence monotonicity: weighted-SSE non-increasing each sweep
- Reproducibility: same seed → factors agree to 1e-5
