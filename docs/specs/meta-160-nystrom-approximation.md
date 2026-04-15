# META-160 — Nyström Kernel Approximation

## Overview
**Category:** Kernel method (low-rank Gram approximation)
**Extension file:** `nystrom.cpp`
**Replaces/improves:** Exact n×n Gram construction inside META-152 (kernel PCA), META-158 (KRR), META-159 (SVR) for large n
**Expected speedup:** ≥20x vs. full Gram for `n ≥ 10000, m ≤ 512`
**RAM:** <80 MB | **Disk:** <1 MB

## Algorithm

```
Input: X ∈ ℝ^{n×d}, kernel k, landmark count m (m ≪ n), strategy
Output: approximated Gram K̂ = C·W⁻¹·Cᵀ or feature map Ψ ∈ ℝ^{n×m}

Landmark selection:
    strategy ∈ { uniform_random, leverage_score, k_means_anchor }
    pick m indices I = {i_1..i_m}

Sub-blocks:
    C = K[:, I]               // n × m
    W = K[I, I]               // m × m principal sub-matrix

Approximation:
    K̂ = C · W⁻¹ · Cᵀ

Rank-m feature map:
    W = U·Σ·Uᵀ  (symmetric eigen)
    Ψ = C · U · Σ^(−1/2)       // n × m, so K̂ = Ψ·Ψᵀ
```

- **Time complexity:** O(n·m·d) to form C, O(m³) for W eigen, O(n·m²) for Ψ
- **Space complexity:** O(n·m) instead of O(n²) — the whole point
- **Convergence:** Spectral error bounded by `O(n/m)·λ_{m+1}(K)` (Williams & Seeger 2001)

## Academic Source
Williams, C. K. I., & Seeger, M. (2001). "Using the Nyström Method to Speed Up Kernel Machines." *Advances in Neural Information Processing Systems 13 (NIPS)*, 682–688.

## C++ Interface (pybind11)

```cpp
struct NystromResult {
    std::vector<float> feature_map;   // n*m row-major (Ψ)
    std::vector<int> landmark_indices; // m
    std::vector<float> W_inv_sqrt;    // m*m (cached for out-of-sample)
    int m, d;
};
NystromResult nystrom_fit(
    const float* X, int n, int d, int m,
    const char* kernel, float gamma, float degree, float coef0,
    const char* strategy,       // "uniform" | "leverage" | "kmeans"
    uint32_t seed
);
std::vector<float> nystrom_transform(
    const NystromResult& model,
    const float* X_train, int n_train, int d,
    const float* X_new,   int n_new,
    const char* kernel, float gamma, float degree, float coef0
);
```

## Memory Budget
- Runtime RAM: <80 MB for n=100k, m=512, d=256
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*m + m*m)`, `alignas(64)` on C and Ψ

## Performance Target
- Python baseline: `sklearn.kernel_approximation.Nystroem(n_components=m).fit_transform(X)`
- Target: ≥20x faster than full Gram (which is untractable for n=100k); ≥3x faster than sklearn Nyström
- Benchmark sizes: (n=5k, m=64, d=32), (n=50k, m=256, d=128), (n=100k, m=512, d=256)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. C-matrix OpenMP over rows with `schedule(static)`.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. `reserve(n*m)` before fill.

**Object lifetime:** Self-assignment safe. No dangling views. Landmark indices copied into model.

**Type safety:** Explicit `static_cast` narrowing with comment. `m < n` validated. Strategy enum validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on C, Ψ. SLEEF `exp()` for RBF.

**Floating point:** FTZ on init. NaN/Inf entry checks. Double accumulator for C row fills. Regularise W before inversion (`W + ε·I`, `ε = 1e-8`).

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all. Singular W raises `LinAlgError` suggesting different landmarks.

**Build:** No cyclic includes. Anonymous namespace for kernel + sampling helpers.

**Security:** No `system()`. No `printf(user_string)`. RNG seed documented. Seed=0 rejected.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_160.py` | `‖K − K̂‖_F / ‖K‖_F ≤ 0.1` for m=n/10 on random Gaussian data |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥3x faster than sklearn Nyström at all sizes |
| 5 | `pytest test_edges_meta_160.py` | m=1, m=n, duplicate landmarks, singular W handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- LAPACK (`ssyevd` for W eigen)
- BLAS (`sgemm` for C·U·Σ^(-1/2))
- Optional: META-151 (PCA) weights if leverage-score sampling chosen

## Pipeline Stage & Non-Conflict
- **Stage:** Kernel-method pre-processing (low-rank Gram)
- **Owns:** Low-rank data-driven Gram approximation for any kernel method at large n
- **Alternative to:** META-161 (RFF — only works for shift-invariant kernels; RFF is data-oblivious)
- **Coexists with:** META-152, META-158, META-159 — all can consume Ψ in place of full K

## Test Plan
- Low-rank input: exact recovery when m ≥ rank(K)
- Approximation error: `‖K − K̂‖_F / ‖K‖_F ≤ 0.1` at m=100, n=1000 for RBF kernel
- Strategy comparison: k_means_anchor ≤ uniform error on clustered data
- Landmark uniqueness: duplicate landmarks yield warning and de-duplication
- Out-of-sample: Ψ(x*) consistent with retraining including x*
