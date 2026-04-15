# META-154 — Sparse PCA

## Overview
**Category:** Dimensionality reduction (linear, sparsity-constrained)
**Extension file:** `sparse_pca.cpp`
**Replaces/improves:** `sklearn.decomposition.SparsePCA` for interpretable feature compaction in the ranker
**Expected speedup:** ≥4x over scikit-learn for `d ≤ 1024, k ≤ 64`
**RAM:** <80 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{n×d}, rank k, ℓ1 penalty λ, ℓ2 penalty α
Output: loadings V ∈ ℝ^{d×k} with many zero entries

Minimise:
    L(U, V) = ‖X − X·U·Vᵀ‖_F² + λ·Σ_j ‖U_j‖₁ + α·‖U‖_F²
    s.t. VᵀV = I_k                       // orthonormal scores

Block-coordinate descent (Zou, Hastie, Tibshirani 2006):
    init V ← top-k PCA loadings
    repeat:
        // Step 1 — update U by elastic-net regression
        for j = 1..k:
            U_j ← argmin ‖X·V_j − X·U_j‖² + λ·‖U_j‖₁ + α·‖U_j‖²
                  (coordinate descent with soft-thresholding)

        // Step 2 — update V by reduced-rank Procrustes
        compute SVD of XᵀX·U = Ã·Σ̃·B̃ᵀ
        V ← Ã · B̃ᵀ
    until ‖V_new − V_old‖_F < tol
```

- **Time complexity:** O(max_iter · (n·d·k + d·k²)) per sweep
- **Space complexity:** O(n·d + d·k) — X dominates
- **Convergence:** Monotonic decrease of L; local minimum (non-convex in V)

## Academic Source
Zou, H., Hastie, T., & Tibshirani, R. (2006). "Sparse Principal Component Analysis." *Journal of Computational and Graphical Statistics*, 15(2), 265–286.

## C++ Interface (pybind11)

```cpp
struct SparsePCAResult {
    std::vector<float> components;      // d*k row-major
    std::vector<float> transformed;     // n*k row-major
    std::vector<float> mean;            // d
    int n_iter;
    float final_loss;
};
SparsePCAResult sparse_pca_fit_transform(
    const float* X, int n, int d, int k,
    float alpha_l1, float alpha_l2,
    int max_iter, float tol, uint32_t seed
);
```

## Memory Budget
- Runtime RAM: <80 MB for n=50k, d=1024, k=64
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d*k)`, `alignas(64)` on U/V

## Performance Target
- Python baseline: `sklearn.decomposition.SparsePCA(n_components=k, alpha=λ).fit(X)`
- Target: ≥4x faster via SIMD soft-thresholding + LAPACK SVD in Procrustes step
- Benchmark sizes: (n=1k, d=64, k=8), (n=10k, d=256, k=32), (n=50k, d=1024, k=64)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Coordinate descent sweeps single-threaded (RNG stability); outer loop OpenMP-safe.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling views. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` narrowing with comment. `alpha ≥ 0` validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on U/V. Vectorised soft-threshold kernel.

**Floating point:** FTZ on init. NaN/Inf entry check. Double accumulator for loss reductions. Zero-detection uses `|u| < 1e-8` tolerance, not exact zero.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Non-convergence returns warning bit.

**Build:** No cyclic includes. Anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. RNG seed documented.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_154.py` | Loss within 1% of sklearn, sparsity pattern ≥95% overlap |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥4x faster at all 3 sizes |
| 5 | `pytest test_edges_meta_154.py` | λ=0 matches PCA, λ=∞ yields zero loadings, n<d handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK/BLAS (`sgesvd` for Procrustes step, `sgemm` for products)
- META-151 (PCA) — initial V comes from PCA loadings

## Pipeline Stage & Non-Conflict
- **Stage:** Feature engineering (interpretable compaction)
- **Owns:** Sparse loadings for interpretable features (each component uses few original dims)
- **Alternative to:** META-151 (dense PCA), META-155 (LDA — supervised)
- **Coexists with:** META-158 (kernel ridge) — sparse loadings can seed feature subset

## Test Plan
- λ=0 degenerate: output matches META-151 (PCA) within 1e-4
- Sparsity control: increasing λ monotonically increases zero count in U
- Deterministic with seed: identical output across runs
- All-zero input: loadings undefined → explicit ValueError
- Rank preservation: sparsity pattern from 2-block input groups dims by block
