# META-151 — Principal Component Analysis (PCA)

## Overview
**Category:** Dimensionality reduction (linear, unsupervised)
**Extension file:** `pca.cpp`
**Replaces/improves:** `sklearn.decomposition.PCA` calls in embedding post-processing and feature compaction
**Expected speedup:** ≥5x over scikit-learn for `d ≤ 1024, k ≤ 128`
**RAM:** <40 MB | **Disk:** <1 MB

## Algorithm

```
Input: data matrix X ∈ ℝ^{n×d}, target rank k
Output: projection V ∈ ℝ^{d×k}, transformed Z ∈ ℝ^{n×k}

1. μ ← (1/n) · Σ_i x_i
2. X̄ ← X − 1·μᵀ                           // mean-center rows
3. Σ ← (1/n) · X̄ᵀ · X̄                     // d×d covariance
4. (λ, V) ← eig(Σ)                         // symmetric eigen-decomposition
5. sort eigenpairs by |λ| descending
6. V_k ← first k columns of V
7. Z ← X̄ · V_k                             // transform: z = Vᵀ·x (per row)
```

- **Time complexity:** O(n·d² + d³) for covariance eigen-decomp; O(n·d·k) for transform
- **Space complexity:** O(d² + n·k) — covariance matrix dominates for large d
- **Convergence:** Exact (closed-form linear algebra); no iteration required

## Academic Source
Pearson, K. (1901). "On lines and planes of closest fit to systems of points in space." *Philosophical Magazine*, 2(11), 559–572.

## C++ Interface (pybind11)

```cpp
// Fit PCA and return top-k principal components + transformed data
struct PCAResult {
    std::vector<float> components;   // d*k row-major
    std::vector<float> explained_variance;  // k
    std::vector<float> mean;         // d
    std::vector<float> transformed;  // n*k row-major
};
PCAResult pca_fit_transform(
    const float* X, int n, int d, int k,
    bool whiten
);
```

## Memory Budget
- Runtime RAM: <40 MB for n=100k, d=1024, k=128 (covariance 4 MB + centered X 400 MB peak — streamed in blocks)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d*d + n*k)`, `alignas(64)` on Σ

## Performance Target
- Python baseline: `sklearn.decomposition.PCA(n_components=k).fit_transform(X)`
- Target: ≥5x faster via direct LAPACK `ssyevd` + blocked `sgemm` for covariance
- Benchmark sizes: (n=1k, d=64, k=16), (n=10k, d=256, k=32), (n=100k, d=1024, k=128)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` predicate form. Atomic memory ordering documented. Spinlocks `_mm_pause()` with 1000-iter fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills. Covariance matrix owned by `std::vector` not raw pointer.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict-aliasing violation.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Max 12 YMM. `alignas(64)` on covariance + components.

**Floating point:** FTZ on init. NaN/Inf entry check on X. Double accumulator for covariance reductions (n > 100).

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `std::move`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. LAPACK info code checked.

**Build:** No cyclic includes. Anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_151.py` | Components match sklearn within 1e-4 (up to sign) |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than sklearn at all 3 sizes |
| 5 | `pytest test_edges_meta_151.py` | n<k, constant column, NaN, single row all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races (if OpenMP enabled) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK (`ssyevd` for symmetric eigen) — already linked via existing extensions
- BLAS (`sgemm` for covariance + transform)

## Pipeline Stage & Non-Conflict
- **Stage:** Feature engineering / embedding compaction (pre-ranking)
- **Owns:** Dense linear dimensionality reduction for real-valued feature matrices
- **Alternative to:** META-152 (kernel PCA, non-linear), META-157 (random projection, no data scan)
- **Coexists with:** META-146 (RFF — acts on PCA output), META-04 (coordinate ascent — operates in reduced space)

## Test Plan
- Identity check: PCA of orthogonal matrix returns identity components (up to sign)
- Rank recovery: rank-r input (n>r, d>r) recovers r non-zero eigenvalues, rest ≤1e-6
- Whitening: whiten=true produces `cov(Z) ≈ I_k` within 1e-3
- NaN/Inf input: raises ValueError before LAPACK call
- n<k edge: returns only min(n,d) components with warning
