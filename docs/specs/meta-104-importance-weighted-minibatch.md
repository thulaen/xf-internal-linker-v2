# META-104 — Importance-Weighted Mini-Batch Sampling

## Overview
**Category:** Variance-reduced sampling (P12 robustness & sampling block)
**Extension file:** `importance_minibatch.cpp`
**Replaces/improves:** Uniform mini-batch sampling — drawing examples with probability proportional to per-example gradient norm and reweighting by 1/p_i yields an unbiased gradient estimate with provably lower variance, accelerating convergence
**Expected speedup:** ≥5x over Python sampling + reweighting loop
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: per-example gradient-norm proxy g_i (e.g. ‖∇ℓ_i(w_current)‖₂),
       mini-batch size m, dataset size N
Output: sampled indices I_1..I_m and weights c_1..c_m for unbiased aggregation

Sampling probabilities (paper Section 3):
  p_i = g_i / Σ_j g_j           (importance proportional to gradient norm)

Sample without replacement from p:
  I_t ∼ p (alias method or sequential sampling)

Importance weights for unbiased gradient estimate:
  c_t = 1 / (m · p_{I_t})
  ∇̂ L(w) = Σ_{t=1..m} c_t · ∇ℓ_{I_t}(w)
  E[∇̂ L] = ∇ L exactly (unbiased)

Variance vs uniform (paper Theorem 1):
  Var(∇̂_importance) ≤ Var(∇̂_uniform), with equality only when all g_i are equal.
```

- **Time complexity:** O(N) to build alias table once per epoch (Walker O(N) construction); O(1) per sample
- **Space complexity:** O(N) for probability table
- **Convergence:** SGD with unbiased gradient estimator → standard SGD theory applies; lower variance gives better empirical convergence

## Academic source
Csiba, D. and Richtárik, P., "Importance Sampling for Minibatches", arXiv:1602.02283 / journal version arXiv:1805.07929, 2018.

## C++ Interface (pybind11)

```cpp
// Build alias-method sampler from probability/weight vector
class AliasSampler {
public:
    AliasSampler(const float* weights, int N, uint64_t rng_seed);
    int  sample();                     // O(1) per draw
    void rebuild(const float* weights, int N);
};

// One-shot importance-weighted mini-batch
struct ImpBatch { std::vector<int> indices; std::vector<float> weights; };

ImpBatch importance_minibatch(
    const float* grad_norms, int N,
    int m, uint64_t rng_seed,
    bool with_replacement = false
);
```

## Memory Budget
- Runtime RAM: <8 MB at N=1e6 (alias table = N · sizeof(int) + N · sizeof(float))
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: alias table allocated once per `rebuild`; per-sample is allocation-free

## Performance Target
- Python baseline: `np.random.choice(N, m, p=p, replace=False)` (cumulative-sum + searchsorted, O(N + m·log N))
- Target: ≥5x faster on N=1e5, m=64 (alias method O(1) per sample)
- Benchmark: 3 sizes — (N, m) ∈ {(1e3, 16), (1e5, 64), (1e7, 256)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Sampler is single-thread; users instantiate per worker.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate N ≥ 1, m ≥ 1, all weights ≥ 0, weight sum > 0.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Walker alias-table construction has data-dependent branches (scalar); per-sample is also scalar (RNG-bound).

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Probability normalisation uses `double` for partition sum when N > 1e5.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. xoshiro256** PRNG embedded.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. All-zero weights raises (degenerate). Negative weights raises. m > N (without-replacement) raises.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. RNG explicitly seeded.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_104.py` | Sampling distribution matches `np.random.choice(p)` within χ² test (p > 0.01) over 1e5 draws |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_importance.py` | ≥5x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_104.py` | uniform weights, single-spike, m=N (without-replacement), m=1, all-zero raises |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | Unbiasedness | E[Σ c_t · g_{I_t}] = Σ g_i within Monte Carlo error over many batches |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps; embed xoshiro256** PRNG and Walker alias method

## Pipeline stage non-conflict declaration
- **Owns:** Walker alias-method sampler + importance-weighted mini-batch construction
- **Alternative to:** Uniform mini-batch sampling, META-102 OHEM (deterministic top-k vs probabilistic)
- **Coexists with:** META-103 reservoir, META-105 stratified k-fold, all P8/P9/P10/P11 metas; the importance weights compose linearly with any other reweighting (DRO, OHEM)

## Test Plan
- Uniform weights: degenerates to uniform sampling
- Single-spike weight on one index: sampler always returns that index, c = N/m
- Without-replacement m = N: returns each index exactly once
- Verify Σ c_t · g_{I_t} unbiased estimate of Σ g_i across many independent batches
- Negative weight raises ValueError
