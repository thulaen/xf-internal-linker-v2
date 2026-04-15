# META-152 — Kernel PCA

## Overview
**Category:** Dimensionality reduction (non-linear, unsupervised)
**Extension file:** `kernel_pca.cpp`
**Replaces/improves:** `sklearn.decomposition.KernelPCA` calls for non-linear feature spaces in reranker
**Expected speedup:** ≥4x over scikit-learn for `n ≤ 5000`
**RAM:** <200 MB | **Disk:** <1 MB

## Algorithm

```
Input: data X ∈ ℝ^{n×d}, kernel k(·,·), target rank k
Output: projection coefficients α ∈ ℝ^{n×k}, transform function φ_k(·)

1. Build Gram matrix:  K_ij = k(x_i, x_j)              // n×n
2. Center in feature space:
       1_N = (1/n) · ones(n,n)
       K̃ = K − 1_N·K − K·1_N + 1_N·K·1_N
3. Eigen-decompose K̃:  K̃ · α_l = λ_l · α_l
4. Sort eigenpairs by λ descending, keep top k
5. Normalize: α_l ← α_l / √(n · λ_l)           // unit-norm in feature space
6. Transform novel x:
       z_k(x) = Σ_i α_{k,i} · k(x_i, x)   (with the same centering correction)
```

- **Time complexity:** O(n²·d) to form K, O(n³) eigen-decomposition, O(n·k) per new-point transform
- **Space complexity:** O(n²) for Gram matrix — main cost
- **Convergence:** Exact (closed-form); truncation via top-k eigenpairs

## Academic Source
Schölkopf, B., Smola, A., & Müller, K.-R. (1998). "Nonlinear component analysis as a kernel eigenvalue problem." *Neural Computation*, 10(5), 1299–1319.

## C++ Interface (pybind11)

```cpp
struct KernelPCAResult {
    std::vector<float> alpha;       // n*k row-major
    std::vector<float> eigenvalues; // k
    std::vector<float> K_row_mean;  // n  (stored for out-of-sample)
    float K_grand_mean;
};
KernelPCAResult kernel_pca_fit(
    const float* X, int n, int d, int k,
    const char* kernel,    // "rbf" | "poly" | "linear"
    float gamma, float degree, float coef0
);
std::vector<float> kernel_pca_transform(
    const KernelPCAResult& model,
    const float* X_train, int n, int d,
    const float* X_new,   int m,
    const char* kernel, float gamma, float degree, float coef0
);
```

## Memory Budget
- Runtime RAM: <200 MB for n=5000 (Gram matrix 100 MB + centered copy 100 MB)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*n)`, `alignas(64)` on Gram

## Performance Target
- Python baseline: `sklearn.decomposition.KernelPCA(kernel='rbf', n_components=k).fit_transform(X)`
- Target: ≥4x faster via SIMD RBF inner loop + LAPACK `ssyevd`
- Benchmark sizes: (n=500, d=32, k=8), (n=2000, d=128, k=32), (n=5000, d=256, k=64)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Atomic ordering documented. OpenMP parallelisation of Gram matrix uses `schedule(static)`.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. RAII only. `reserve(n*n)` for Gram. Out-of-memory detected before allocation for large n.

**Object lifetime:** Self-assignment safe. No dangling views. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` narrowing with comment. Kernel type enum validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on Gram. `exp()` vectorised via SLEEF or polynomial approx (document choice).

**Floating point:** FTZ on init. NaN/Inf entry check on X. Double accumulator for Gram row sums. Clamp RBF exponent to avoid underflow.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. LAPACK info code checked.

**Build:** No cyclic includes. Anonymous namespace for kernel dispatch. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_152.py` | Output matches sklearn KernelPCA within 1e-3 (up to sign) |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥4x faster at all 3 sizes |
| 5 | `pytest test_edges_meta_152.py` | n=1, duplicate rows, invalid kernel string all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK (`ssyevd`)
- BLAS (`sgemm` for centering)
- META-151 (PCA) — linear kernel path delegates to linear PCA for parity

## Pipeline Stage & Non-Conflict
- **Stage:** Feature engineering (pre-ranking non-linear compaction)
- **Owns:** Non-linear kernel-based dimensionality reduction
- **Alternative to:** META-151 (linear PCA), META-157 (JL random projection)
- **Coexists with:** META-160 (Nyström approximation — provides cheaper K̂), META-161 (RFF — different kernel-approx path)

## Test Plan
- Linear kernel sanity: linear kernel output matches META-151 within 1e-4
- RBF on concentric circles: top 2 components separate the rings
- Out-of-sample parity: refitting on train+test matches transform-of-test within 1e-3
- Invalid kernel name: raises ValueError
- Zero-variance input: returns zero components without NaN
