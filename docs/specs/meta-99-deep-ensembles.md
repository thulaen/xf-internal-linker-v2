# META-99 — Deep Ensembles

## Overview
**Category:** Independent-run ensemble + uncertainty (P11 model averaging block)
**Extension file:** `deep_ensembles.cpp`
**Replaces/improves:** Single-model prediction without uncertainty estimate — deep ensembles train N independent networks from different random seeds and average their outputs; variance across the ensemble is a principled epistemic-uncertainty signal
**Expected speedup:** ≥5x over Python ensemble averaging + variance computation
**RAM:** <2N · model size | **Disk:** N model checkpoints

## Algorithm

```
Input: N independent models trained from different random seeds (also random
       data-shuffling seeds and, for paper-faithful version, adversarial training)
Output: P(y | x) and Var[P_n(y | x)] (epistemic uncertainty)

Per query x:
  for n = 1..N:
      p_n(y | x) ← model_n(x)            // independent forward passes
  mean:    P(y | x) = (1/N) · Σ_n p_n(y | x)
  variance (per class y):
           σ²(y | x) = (1/N) · Σ_n (p_n(y | x) − P(y | x))²

Optional per-paper extras:
  - Each model trained with adversarial loss term (Goodfellow et al. FGSM augment)
  - Predictive distribution: mixture of Gaussians for regression heads
```

- **Time complexity:** O(N) inference cost per query (embarrassingly parallel)
- **Space complexity:** O(N · d) on disk; in-memory N prediction vectors per query
- **Convergence:** N=5 typically near-optimal on classification; diminishing returns past N=10

## Academic source
Lakshminarayanan, B., Pritzel, A. and Blundell, C., "Simple and Scalable Predictive Uncertainty Estimation using Deep Ensembles", *Advances in Neural Information Processing Systems (NIPS)*, 2017.

## C++ Interface (pybind11)

```cpp
// Per-query mean + variance over N predictions of length C
struct EnsembleOut {
    std::vector<float> mean;       // length C
    std::vector<float> variance;   // length C
};

EnsembleOut deep_ensemble_combine(
    const float* probs_NxC, int N, int C
);

// Optional: log-mixture for proper-scoring-rule style aggregation
void deep_ensemble_log_mixture(
    const float* log_probs_NxC, int N, int C,
    float* log_mix_out
);
```

## Memory Budget
- Runtime RAM: <2N · C floats per query (input N×C + output 2C)
- Disk: N · model size for checkpoints
- Allocation: pre-sized output buffers; no per-query alloc

## Performance Target
- Python baseline: NumPy `np.mean` + `np.var` over a stack
- Target: ≥5x faster on N=5, C=10000 (single-pass two-moment update)
- Benchmark: 3 sizes — (N, C) ∈ {(3, 100), (5, 10000), (10, 100000)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate N ≥ 1, C ≥ 1.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Welford two-pass mean+variance vectorised across C.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for variance (mean of squared deviations) when N · C > 1e6. Use Welford one-pass to avoid catastrophic cancellation in `E[p²] − (E[p])²`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Single pass over the N×C matrix computes both mean and variance.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. N=0 raises. N=1 returns variance=0 (not NaN from 1/(N-1)).

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU on checkpoint paths.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_99.py` | mean and variance match NumPy within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_deep_ensemble.py` | ≥5x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_99.py` | N=1 (var=0), N=2, C=1, identical predictions, NaN handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | OOD detection | Synthetic OOD inputs produce higher variance than in-distribution (paper claim) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps

## Pipeline stage non-conflict declaration
- **Owns:** Mean + variance aggregation across N independent runs (epistemic uncertainty estimate)
- **Alternative to:** META-96 SWA, META-97 Polyak-Ruppert (single-run weight averaging), META-98 snapshot ensemble (single-run prediction averaging)
- **Coexists with:** Calibration metas (META-87 to META-90) — apply calibration to ensemble mean P(y|x); LR schedulers; P8 regularisers

## Test Plan
- N=1: verify mean = input, variance = 0 (no division-by-zero)
- N identical predictions: verify variance = 0
- Antithetic predictions p and 1−p with N=2: verify mean = 0.5, variance = paper formula
- Welford one-pass vs two-pass NumPy: numerical agreement within 1e-7
- OOD smoke test: variance grows with input perturbation magnitude
