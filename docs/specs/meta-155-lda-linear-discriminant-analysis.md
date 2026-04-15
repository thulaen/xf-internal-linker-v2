# META-155 — Linear Discriminant Analysis (LDA)

## Overview
**Category:** Dimensionality reduction (linear, supervised)
**Extension file:** `lda.cpp`
**Replaces/improves:** `sklearn.discriminant_analysis.LinearDiscriminantAnalysis` for class-aware projection of relevance-labelled features
**Expected speedup:** ≥5x over scikit-learn for `d ≤ 1024, C ≤ 50`
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{n×d}, labels y ∈ {0..C−1}^n, target rank k ≤ C−1
Output: projection W ∈ ℝ^{d×k}, transformed Z = X·W

1. Per-class means:      μ_c = (1/n_c) · Σ_{y_i=c} x_i
   Global mean:          μ   = (1/n) · Σ_i x_i

2. Within-class scatter:
       S_W = Σ_c Σ_{y_i=c} (x_i − μ_c)(x_i − μ_c)ᵀ

3. Between-class scatter:
       S_B = Σ_c n_c · (μ_c − μ)(μ_c − μ)ᵀ

4. Fisher discriminant:
       J(w) = (wᵀ · S_B · w) / (wᵀ · S_W · w)

5. Solve generalised eigen-problem:
       S_B · w = λ · S_W · w          ⇔  eig(S_W⁻¹ · S_B)

6. Sort by λ descending, keep top k columns → W
7. Transform: Z = (X − μ) · W
```

- **Time complexity:** O(n·d² + C·d² + d³) — scatter matrices + eigen-decomp
- **Space complexity:** O(d² + C·d)
- **Convergence:** Exact (closed-form generalised eigen)

## Academic Source
Fisher, R. A. (1936). "The use of multiple measurements in taxonomic problems." *Annals of Eugenics*, 7(2), 179–188.

## C++ Interface (pybind11)

```cpp
struct LDAResult {
    std::vector<float> components;    // d*k row-major (W)
    std::vector<float> class_means;   // C*d row-major
    std::vector<float> mean;          // d
    std::vector<float> explained_variance_ratio; // k
};
LDAResult lda_fit_transform(
    const float* X, const int* y,
    int n, int d, int n_classes, int k,
    float shrinkage   // 0.0 = none, (0,1] = diagonal shrinkage for S_W
);
```

## Memory Budget
- Runtime RAM: <30 MB for n=100k, d=1024, C=20, k=16
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d*d + C*d)`, `alignas(64)` on scatter matrices

## Performance Target
- Python baseline: `sklearn.LinearDiscriminantAnalysis(solver='eigen', n_components=k).fit_transform(X, y)`
- Target: ≥5x faster via direct LAPACK `ssygvd` (generalised symmetric eigen)
- Benchmark sizes: (n=1k, d=64, C=5, k=4), (n=10k, d=256, C=10, k=8), (n=100k, d=1024, C=20, k=16)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Scatter accumulation uses OpenMP with per-thread buffers reduced at end.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling views. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` narrowing with comment. Label range `[0, n_classes)` validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on S_W and S_B.

**Floating point:** FTZ on init. NaN/Inf entry check on X. Double accumulator for scatter reductions. Shrinkage applied only if S_W near-singular (`cond > 1e10`).

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. LAPACK info code checked — singular S_W raises `LinAlgError`.

**Build:** No cyclic includes. Anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_155.py` | Components match sklearn within 1e-4 (up to sign) |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥5x faster at all 3 sizes |
| 5 | `pytest test_edges_meta_155.py` | Single class, n_c<d, k>C−1, empty class all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK (`ssygvd` generalised symmetric eigen)
- BLAS (`sgemm` for scatter matrix products)

## Pipeline Stage & Non-Conflict
- **Stage:** Supervised feature engineering (uses relevance labels)
- **Owns:** Class-discriminative linear projection when labels available
- **Alternative to:** META-151 (PCA — unsupervised), META-156 (CCA — two views)
- **Coexists with:** META-158 (kernel ridge — LDA output as input features)

## Test Plan
- Iris parity: verify k=2 projection separates 3 Iris classes with ≥95% linear-separability
- Single-class input: raises `ValueError("LDA requires ≥2 classes")`
- k > C−1: clipped to C−1 with warning
- Label out of range: raises `ValueError`
- Singular S_W: auto-shrinkage kicks in and solver still returns components
