# META-113 — Sequential Monte Carlo (SMC / Particle Filter)

## Overview
**Category:** Particle-based posterior sampler (tempered, parallelizable)
**Extension file:** `smc.cpp`
**Replaces/improves:** Single-chain MCMC when posterior is multi-modal or annealing is needed
**Expected speedup:** ≥7x over Python particle loop
**RAM:** <50 MB | **Disk:** <1 MB

## Algorithm

```
Input: target π, prior q_0, tempering schedule {β_k}, n_particles N
Output: weighted particles {w_i, W_i}_{i=1..N} approximating π

# particle set {w_i, W_i}; resample proportional to W_i, propagate via transition kernel, reweight
initialize w_i ~ q_0, W_i ← 1/N
for k = 1..K:
    # reweight toward β_k tempered target
    W_i ∝ W_i · (π(w_i) / π_{β_{k-1}}(w_i))^{β_k - β_{k-1}}
    normalize W
    if ESS(W) < N/2:
        resample {w_i} ∝ W_i (systematic), reset W_i ← 1/N
    # propagate via MCMC kernel (MH or HMC) at temperature β_k
    for i = 1..N:
        w_i ← transition_kernel(w_i, β_k)
return {w_i, W_i}
```

- **Time complexity:** O(K × N × kernel_cost)
- **Space complexity:** O(N × d)
- **Convergence:** Feynman-Kac; effective sample size (ESS) controls variance

## Academic Source
Del Moral P. "Non-linear filtering: interacting particle solution." *Comptes Rendus de l'Académie des Sciences Paris, Série I* 325(6):653–658, 1996. (Later unified in Del Moral, Doucet, Jasra, JRSS-B 2006, DOI: 10.1111/j.1467-9868.2006.00553.x.)

## C++ Interface (pybind11)

```cpp
// SMC sampler with tempered annealing and systematic resampling
std::pair<std::vector<std::vector<float>>, std::vector<float>> smc_sample(
    int n_particles, int d,
    std::function<void(float*)> sample_prior,
    std::function<float(const float*)> log_target,
    std::function<void(float*, float)> transition_kernel,  // in-place MCMC step at β
    const float* temperature_schedule, int n_steps,
    uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <50 MB (N=10k particles × d=200 floats + weights)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: contiguous particle arena `alignas(64)`

## Performance Target
- Python baseline: numpy particle loop + scipy resampling
- Target: ≥7x faster
- Benchmark: N ∈ {1k, 10k, 50k} × K=20 × d ∈ {10, 50}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Particle propagation may use OpenMP with per-thread RNG state.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Resampling uses stable reindex, not realloc.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on particle array. Vectorize weight normalization.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Log-sum-exp for weight normalization. Double accumulator for ESS.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Degenerate particle set (ESS → 0) raises warning.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG per particle lane.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_113.py` | Posterior mean matches MCMC within 5% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_113.py` | Degenerate ESS, multi-modal, N=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Optional: reuses transition kernels from META-106 / META-109
- Optional RNG utility from META-106

## Pipeline Stage Non-Conflict
**Owns:** Multi-modal posterior approximation via tempered particle populations.
**Alternative to:** Single-chain MCMC (META-106..110) when modes are well-separated.
**Coexists with:** All MCMC kernels — SMC can wrap them as transition step.

## Test Plan
- Bimodal Gaussian mix: both modes captured with correct weight
- Unimodal reference: results within 5% of MH
- Resampling invariant: sum(W) = 1 ± 1e-6 after normalization
- N=1 edge case: reduces to importance sampling
