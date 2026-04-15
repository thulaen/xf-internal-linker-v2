# META-161 — Random Fourier Features for Gaussian-Kernel Regression

## Overview
**Category:** Kernel method (shift-invariant kernel approximation)
**Extension file:** `rff_kernel.cpp`
**Replaces/improves:** Full Gram construction in META-158 (KRR) and META-159 (SVR) when the chosen kernel is Gaussian/RBF; enables primal-space solvers
**Expected speedup:** ≥8x vs. exact KRR for `n ≥ 20000, D ≤ 2048`
**RAM:** <100 MB | **Disk:** <1 MB
**Note:** This is the **kernel-approximation** use of RFF. META-146 uses the same paper for linear-predictor primalisation — different application, same primitive.

## Algorithm

```
Input: X ∈ ℝ^{n×d}, RBF kernel with bandwidth σ, target feature dim D
Output: feature map Z ∈ ℝ^{n×D} s.t. k(x, y) ≈ z(x)ᵀ·z(y)

Bochner's theorem: a shift-invariant kernel k(x−y) is the Fourier transform
of a non-negative measure p(ω). For Gaussian kernel with bandwidth σ:
    p(ω) = N(0, σ⁻²·I_d)

Sampling step:
    ω_i ~ N(0, σ⁻²·I_d)   for i = 1..D
    b_i ~ Uniform[0, 2π]

Feature map:
    z(x) = √(2/D) · [ cos(ω₁ᵀx + b₁), cos(ω₂ᵀx + b₂), …, cos(ω_Dᵀx + b_D) ]ᵀ

Guarantee (Rahimi & Recht 2007, Claim 1):
    E[z(x)ᵀ·z(y)] = k(x − y)
    Pr[ |z(x)ᵀz(y) − k(x−y)| > ε ] ≤ O(exp(−D·ε²))

Downstream use:
    Replace full Gram K with Z·Zᵀ (never materialised) inside any kernel method.
    Solve KRR in primal:  w = (ZᵀZ + λ·I_D)⁻¹ · Zᵀy       (size D × D, not n × n)
    Predict:  f(x*) = z(x*)ᵀ · w
```

- **Time complexity:** O(n·d·D) to build Z; O(D³ + n·D²) for primal KRR solve
- **Space complexity:** O(D·d) for ω sample + O(n·D) for Z
- **Convergence:** Probabilistic uniform bound per Claim 1; concentration improves as 1/√D

## Academic Source
Rahimi, A., & Recht, B. (2007). "Random Features for Large-Scale Kernel Machines." *Advances in Neural Information Processing Systems 20 (NIPS)*.
(Note: META-146 applies this primitive to **linear predictor primalisation**; META-161 applies it to **Gaussian-kernel regression approximation** via primal-space KRR/SVR solves — separate code paths, shared underlying randomisation.)

## C++ Interface (pybind11)

```cpp
struct RFFModel {
    std::vector<float> omega;         // D*d row-major
    std::vector<float> bias;          // D
    int D, d;
    float sigma;
};
RFFModel rff_build(int d, int D, float sigma, uint32_t seed);

std::vector<float> rff_transform(
    const RFFModel& model,
    const float* X, int n
);

// Convenience: primal-space kernel ridge regression using RFF
struct RFFKRRModel {
    RFFModel features;
    std::vector<float> weights;    // D
    float bias;
};
RFFKRRModel rff_krr_fit(
    const float* X, const float* y, int n, int d,
    int D, float sigma, float lambda_reg, uint32_t seed
);
std::vector<float> rff_krr_predict(
    const RFFKRRModel& model,
    const float* X_new, int m
);
```

## Memory Budget
- Runtime RAM: <100 MB for n=100k, D=2048, d=256
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n*D)`, `alignas(64)` on Z

## Performance Target
- Python baseline: `sklearn.kernel_approximation.RBFSampler(gamma=σ⁻², n_components=D).fit_transform(X)` followed by ridge
- Target: ≥8x end-to-end vs. exact KRR at n=100k (exact is infeasible); ≥3x vs. sklearn RFF+ridge pipeline
- Benchmark sizes: (n=5k, D=256, d=32), (n=50k, D=1024, d=128), (n=100k, D=2048, d=256)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Z construction OpenMP by row. RNG thread-local with seeded per-thread stream.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. `reserve(n*D)` before fills.

**Object lifetime:** Self-assignment safe. No dangling views. ω, b owned by model.

**Type safety:** Explicit `static_cast` narrowing with comment. `D, σ > 0` validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on Z, ω. SLEEF `cos()` vectorised batch-of-4.

**Floating point:** FTZ on init. NaN/Inf entry checks. Double accumulator for ωᵀx if d > 512. Cosine input unwrapped mod 2π before SLEEF call.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`. Batched SIMD cos over D.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Anonymous namespace for RNG/cos helpers. Shared RNG code with META-146 via static helper (no duplication).

**Security:** No `system()`. No `printf(user_string)`. RNG seed parameter documented. Seed=0 rejected.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_161.py` | `‖K − Z·Zᵀ‖_F / ‖K‖_F ≤ 0.1` for D=1024, n=500 |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥3x faster than sklearn RBFSampler at all sizes |
| 5 | `pytest test_edges_meta_161.py` | D=1, σ very small/large, constant X all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed; no code duplication with META-146 |

## Dependencies
- LAPACK (`spotrf` + `spotrs` for D×D primal solve)
- BLAS (`sgemm`, `sgemv`)
- Shares RNG/cosine helpers with META-146 (do not duplicate)

## Pipeline Stage & Non-Conflict
- **Stage:** Kernel-method pre-processing (shift-invariant-kernel approximation)
- **Owns:** Gaussian-kernel feature map for primal-space KRR/SVR
- **Alternative to:** META-160 (Nyström — data-driven, any kernel; RFF is data-oblivious, shift-invariant only)
- **Coexists with:** META-146 (same primitive, different downstream — linear predictor primalisation), META-158 (KRR — RFF-KRR is a second KRR flavour)
- **Distinct from META-146:** META-146 replaces an existing linear predictor's dot product with `z(x)ᵀ·w`. META-161 replaces a kernel regression's Gram matrix with `Z·Zᵀ` to enable primal-space solves at scale.

## Test Plan
- Gram approximation: `‖K − Z·Zᵀ‖_F / ‖K‖_F ≤ 0.1` at D=1024, n=500, RBF kernel
- Determinism: same seed → identical ω and b
- Bandwidth sweep: `σ → 0` makes all z(x) ≈ constant; `σ → ∞` makes K̂ ≈ I
- Primal vs. dual parity: RFF-KRR predictions match exact KRR within 5% at small n with D ≥ n
- Code review: confirm no copy-paste from META-146 — shared helpers factored out
