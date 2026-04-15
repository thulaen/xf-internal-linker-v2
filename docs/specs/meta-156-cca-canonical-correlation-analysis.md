# META-156 — Canonical Correlation Analysis (CCA)

## Overview
**Category:** Dimensionality reduction (two-view, supervised-by-pairing)
**Extension file:** `cca.cpp`
**Replaces/improves:** `sklearn.cross_decomposition.CCA` for aligning text-embedding view with click-graph view
**Expected speedup:** ≥5x over scikit-learn for `d_x, d_y ≤ 1024`
**RAM:** <40 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{n×d_x}, Y ∈ ℝ^{n×d_y}, target rank k
Output: projections U ∈ ℝ^{d_x×k}, V ∈ ℝ^{d_y×k}

1. Centre: X̄ = X − μ_x,  Ȳ = Y − μ_y
2. Covariances:
       Σ_x  = (1/n)·X̄ᵀ·X̄
       Σ_y  = (1/n)·Ȳᵀ·Ȳ
       Σ_xy = (1/n)·X̄ᵀ·Ȳ

3. Canonical problem — maximise
       corr(Uᵀ·x, Vᵀ·y) = UᵀΣ_xy·V / √(UᵀΣ_x·U · VᵀΣ_y·V)

4. Solved via generalised eigen:
       (Σ_x⁻¹·Σ_xy·Σ_y⁻¹·Σ_yx) · u = ρ² · u
       v = (Σ_y⁻¹·Σ_yx) · u / ρ

5. Sort pairs (u_l, v_l) by ρ_l descending, keep top k
```

- **Time complexity:** O(n·(d_x+d_y)² + (d_x+d_y)³) for covariance + eigen
- **Space complexity:** O(d_x² + d_y² + d_x·d_y)
- **Convergence:** Exact (closed-form generalised eigen)

## Academic Source
Hotelling, H. (1936). "Relations between two sets of variates." *Biometrika*, 28(3–4), 321–377.

## C++ Interface (pybind11)

```cpp
struct CCAResult {
    std::vector<float> U;             // d_x*k row-major
    std::vector<float> V;             // d_y*k row-major
    std::vector<float> correlations;  // k — top canonical correlations
    std::vector<float> mean_x;        // d_x
    std::vector<float> mean_y;        // d_y
};
CCAResult cca_fit(
    const float* X, int n, int d_x,
    const float* Y, int d_y,
    int k, float reg_x, float reg_y   // ridge to stabilise Σ_x⁻¹, Σ_y⁻¹
);
```

## Memory Budget
- Runtime RAM: <40 MB for n=50k, d_x=d_y=512, k=32
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d_x*d_x + d_y*d_y)`, `alignas(64)` on covariance blocks

## Performance Target
- Python baseline: `sklearn.cross_decomposition.CCA(n_components=k).fit(X, Y)`
- Target: ≥5x faster via direct LAPACK `ssygvd` generalised eigen
- Benchmark sizes: (n=1k, d=32, k=8), (n=10k, d=256, k=16), (n=50k, d=512, k=32)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Covariance OpenMP uses reduction buffers.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling views. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` narrowing with comment. `n` must match between X and Y — validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on covariance blocks.

**Floating point:** FTZ on init. NaN/Inf entry check. Double accumulator for covariance. Ridge `reg ≥ 1e-6` enforced when condition number high.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. LAPACK info code checked — singular Σ_x/Σ_y raises `LinAlgError` unless `reg>0`.

**Build:** No cyclic includes. Anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_156.py` | Canonical correlations match sklearn within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥5x faster at all 3 sizes |
| 5 | `pytest test_edges_meta_156.py` | d_x≠d_y, n<max(d_x,d_y), singular Σ with reg=0 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK (`ssygvd` generalised symmetric eigen, `spotrf` Cholesky for reg)
- BLAS (`sgemm` for covariance)

## Pipeline Stage & Non-Conflict
- **Stage:** Multi-view feature engineering (aligning two signal sources)
- **Owns:** Two-view linear alignment (text vs. click-graph, query vs. doc)
- **Alternative to:** META-155 (LDA — class labels), META-151 (PCA — single view)
- **Coexists with:** META-158 (kernel ridge — CCA output as features), META-152 (kernel PCA — different non-linear path)

## Test Plan
- Identity alignment: X=Y returns correlations of 1 for all components
- Orthogonal views: unrelated X,Y returns correlations near 0
- Deterministic output: same seed+input → identical components
- Parity against sklearn CCA for n=1000, d_x=d_y=10, k=5
- Regularisation effect: `reg>0` produces finite components even when Σ singular
