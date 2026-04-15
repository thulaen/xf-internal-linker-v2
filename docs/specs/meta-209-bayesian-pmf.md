# META-209 — Bayesian Probabilistic Matrix Factorisation (BPMF)

## Overview
**Category:** Matrix factorisation (full Bayesian, Gibbs sampling)
**Extension file:** `bpmf.cpp`
**Replaces/improves:** No existing Python reference; eliminates the need to hand-tune λ_U, λ_V in META-208 by marginalising over hyperparameters
**Expected speedup:** ≥8x over reference numpy Gibbs loop
**RAM:** <400 MB for 100k×50k, k=32, 200 posterior samples | **Disk:** <1 MB

## Algorithm

```
Input:  observed ratings R_ij for (i,j) ∈ Ω, rank k
Hyperpriors (paper Eq. 7–8):
  Λ_U ~ Wishart(W₀, ν₀)    μ_U | Λ_U ~ N(μ₀, (β₀·Λ_U)⁻¹)
  Λ_V ~ Wishart(W₀, ν₀)    μ_V | Λ_V ~ N(μ₀, (β₀·Λ_V)⁻¹)

Gibbs sweep (one iteration):
  1. Sample Λ_U, μ_U | U  (Normal-Wishart posterior closed-form)
  2. Sample Λ_V, μ_V | V  (Normal-Wishart posterior closed-form)
  3. For each i: sample U_i | V, Λ_U, μ_U, R  ~ N(μ_i*, Λ_i*⁻¹)
       Λ_i* = Λ_U + α · Σ_{j: (i,j) ∈ Ω} V_j V_jᵀ
       μ_i* = Λ_i*⁻¹ · (α · Σ_j R_ij V_j + Λ_U μ_U)
  4. For each j: sample V_j | U, Λ_V, μ_V, R (symmetric)

Predictive distribution via Monte Carlo:
  p(R_ij* | R) ≈ (1/S) · Σ_{s=1..S}  N(U_i^{(s)ᵀ} V_j^{(s)}, σ²)
```

- **Time complexity:** O(S · (|Ω| · k² + (N + M) · k³))  ; k³ from Cholesky per row/col
- **Space complexity:** O((N + M) · k · S_kept) if storing posterior samples; O((N+M)·k) with running mean
- **Convergence:** No mixing guarantee; monitor via log-posterior trace

## Academic Source
Salakhutdinov, R. & Mnih, A. "Bayesian Probabilistic Matrix Factorization using Markov Chain Monte Carlo." *Proceedings of the 25th International Conference on Machine Learning (ICML 2008)*, 880–887. DOI: 10.1145/1390156.1390267.

## C++ Interface (pybind11)

```cpp
// Full Bayesian PMF via Gibbs; returns posterior mean predictions and samples
struct BPMFResult { py::array_t<float> pred_mean; py::array_t<float> pred_std; };

BPMFResult bpmf_gibbs(
    py::array_t<int32_t> row_idx,
    py::array_t<int32_t> col_idx,
    py::array_t<float>   ratings,
    int N, int M, int k,
    int burn_in = 50, int n_samples = 150,
    float alpha = 2.0f,           // observation precision
    float beta0 = 2.0f, float nu0 = 0.0f,   // Normal-Wishart hyper
    uint64_t seed = 0
);
```

## Memory Budget
- Runtime RAM: <400 MB at N=100000, M=50000, k=32, burn+samples=200 (running sums, no sample archive)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: `reserve((N+M)*k)` + `reserve(k*k)` Cholesky workspace; no per-sweep allocation

## Performance Target
- Baseline: reference numpy Gibbs loop
- Target: ≥8x faster per sweep
- Benchmark: 3 sizes — (1k×1k, |Ω|=50k, k=8, S=100), (10k×5k, |Ω|=500k, k=16, S=150), (100k×50k, |Ω|=5M, k=32, S=200)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** Parallel over users in step 3 (independent Cholesky per row). Per-thread RNG state with splittable seed. Document memory ordering for shared running sums.

**Memory:** No raw `new`/`delete`. Arena for per-thread Cholesky scratch. Bounds-checked indices in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for |Ω| loops.

**SIMD:** AVX2 on V_j V_jᵀ outer-product accumulation. `_mm256_zeroupper()` before return. `alignas(64)` on row blocks.

**Floating point:** Double accumulator on precision matrix sums. NaN/Inf check each sweep. Reject non-positive-definite Λ with fallback jitter ε·I.

**Performance:** No `std::endl`. No `std::function` hot loop. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise on NaN rating, oob index, or Wishart-sample failure.

**Build:** No cyclic includes. Anonymous namespace for sampler helpers.

**Security:** No `system()`. Reproducible seed path only.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_209.py` | Posterior mean RMSE within 3% of reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than numpy Gibbs at all 3 sizes |
| 5 | `pytest test_edges_meta_209.py` | Empty Ω, k=1, NaN, singular Λ fallback all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races on running-sum accumulators |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- May consume META-208 output as warm-start for U, V at iteration 0 (optional)

## Pipeline Stage Non-Conflict
- **Stage owned:** Full posterior over latent factors (uncertainty-aware recommendation)
- **Owns:** Gibbs sampler for (U, V, Λ_U, Λ_V, μ_U, μ_V)
- **Alternative to:** META-208 (point-estimate PMF), META-210 (WALS)
- **Coexists with:** META-206 (SVD seed), META-208 (MAP warm-start)

## Test Plan
- Synthetic data from known Normal-Wishart: verify posterior mean within CI of truth
- Empty Ω: verify raises `py::value_error`
- Non-PD Λ path: verify jitter fallback adds ε·I and recovers
- Reproducibility: same seed → running predictive mean agrees to 1e-4
- Trace monitoring: log-posterior sequence is non-decreasing in expectation after burn-in
