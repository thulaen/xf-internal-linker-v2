# META-153 — Independent Component Analysis (FastICA)

## Overview
**Category:** Dimensionality reduction / blind source separation
**Extension file:** `ica.cpp`
**Replaces/improves:** `sklearn.decomposition.FastICA` for decorrelating embedding dimensions during feature pre-processing
**Expected speedup:** ≥5x over scikit-learn for `d ≤ 512`
**RAM:** <50 MB | **Disk:** <1 MB

## Algorithm

```
Input: data X ∈ ℝ^{n×d}, target components k, non-linearity G (tanh | exp | cube)
Output: mixing W ∈ ℝ^{k×d}, sources S = W · X_whitened

Pre-process:
    center X; whiten via PCA → X_w s.t. cov(X_w) = I_k

FastICA objective (maximise non-Gaussianity):
    J(y) ≈ (E[G(y)] − E[G(ν)])²     where ν ~ N(0,1)

For each component l = 1..k:
    init w_l randomly, ‖w_l‖ = 1
    repeat:
        w_l ← E[ X_w · g(w_lᵀ · X_w) ] − E[ g'(w_lᵀ · X_w) ] · w_l
        w_l ← w_l − Σ_{j<l} (w_lᵀ · w_j) · w_j          // deflation orthogonalisation
        w_l ← w_l / ‖w_l‖
    until |⟨w_l_new, w_l_old⟩| > 1 − tol
```

- **Time complexity:** O(max_iter · k · n · d) per sweep; whitening O(n·d² + d³)
- **Space complexity:** O(n·d + k·d) for whitened data + mixing matrix
- **Convergence:** Cubic under mild conditions (Hyvärinen 1999); fall back on `max_iter` cap

## Academic Source
Hyvärinen, A., & Oja, E. (2000). "Independent component analysis: algorithms and applications." *Neural Networks*, 13(4–5), 411–430.

## C++ Interface (pybind11)

```cpp
struct ICAResult {
    std::vector<float> mixing;    // k*d row-major (W)
    std::vector<float> unmixing;  // d*k row-major (W⁺)
    std::vector<float> sources;   // n*k row-major (S)
    std::vector<float> mean;      // d
    int n_iter;
};
ICAResult fastica_fit_transform(
    const float* X, int n, int d, int k,
    const char* nonlinearity,     // "tanh" | "exp" | "cube"
    int max_iter, float tol, uint32_t seed
);
```

## Memory Budget
- Runtime RAM: <50 MB for n=50k, d=256, k=64
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*d)`, `alignas(64)` on W and X_whitened

## Performance Target
- Python baseline: `sklearn.decomposition.FastICA(n_components=k).fit_transform(X)`
- Target: ≥5x faster via SIMD tanh (SLEEF) + deflation without Python loop overhead
- Benchmark sizes: (n=1k, d=32, k=8), (n=10k, d=128, k=32), (n=50k, d=256, k=64)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. RNG is thread-local.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling views. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` narrowing with comment. Nonlinearity enum validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on W. Vectorised tanh via SLEEF or polynomial.

**Floating point:** FTZ on init. NaN/Inf entry checks. Double accumulator for E[] expectations. Clamp `tanh` input to [−20, 20].

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Non-convergence returns `n_iter = max_iter` with warning bit.

**Build:** No cyclic includes. Anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. RNG seed parameter documented.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_153.py` | Sources match sklearn within 1e-3 after sign/permutation align |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥5x faster at all 3 sizes |
| 5 | `pytest test_edges_meta_153.py` | Gaussian input (no IC), constant column, n<k handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK/BLAS (whitening via `ssyevd` + `sgemm`)
- META-151 (PCA) for whitening step — shared code path

## Pipeline Stage & Non-Conflict
- **Stage:** Feature engineering (decorrelation before ranking)
- **Owns:** Non-Gaussian source separation on pre-whitened features
- **Alternative to:** META-151 (PCA — Gaussian, orthogonal), META-154 (sparse PCA)
- **Coexists with:** META-151 (used internally for whitening), META-162 (GPR — can consume ICA sources)

## Test Plan
- Two-source mixture: recover sources from known 2-source mixing within correlation ≥0.95
- Gaussian input: algorithm emits warning (no independent components exist)
- Deterministic with seed: same seed → bit-identical output across runs
- Non-convergence: synthetic pathological input hits max_iter and flags it
- Whitening check: `cov(X_whitened) ≈ I_k` within 1e-4
