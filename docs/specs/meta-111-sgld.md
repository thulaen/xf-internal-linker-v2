# META-111 — Stochastic Gradient Langevin Dynamics (SGLD)

## Overview
**Category:** MCMC weight posterior sampler (mini-batch, scalable)
**Extension file:** `sgld.cpp`
**Replaces/improves:** Full-batch HMC when data is too large for per-step gradient eval
**Expected speedup:** ≥4x over PyTorch SGLD loop (Python overhead + autograd overhead)
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: mini-batch gradient estimator ∇_w Ũ(w), step schedule ε_t, n_iters
Output: chain {w_t} approximating samples from posterior π(w | D)

for t = 1..n_iters:
    # w_{t+1} = w_t - (ε/2)·∇_w Ũ(w_t) + √ε·ξ_t  where ξ ~ N(0,I)
    g ← grad_minibatch(w, batch)
    ξ ← N(0, I_d)
    w ← w - (ε_t / 2) · g + √ε_t · ξ
    if t > burn_in and t % thin == 0:
        append w to chain
```

- **Time complexity:** O(n_iters × batch_grad_cost)
- **Space complexity:** O(n_samples × d)
- **Convergence:** Biased MCMC; bias → 0 as ε_t → 0 with ∑ε_t = ∞, ∑ε_t² < ∞ (Robbins-Monro)

## Academic Source
Welling M., Teh Y.W. "Bayesian Learning via Stochastic Gradient Langevin Dynamics." *Proceedings of the 28th International Conference on Machine Learning (ICML)* 2011. URL: https://icml.cc/2011/papers/398_icmlpaper.pdf.

## C++ Interface (pybind11)

```cpp
// SGLD with polynomial-decay step size ε_t = a (b + t)^{-γ}
std::vector<std::vector<float>> sgld_sample(
    const float* initial_w, int d,
    std::function<void(const float*, int, float*)> grad_minibatch,
    int n_batches, float step_a, float step_b, float step_gamma,
    int n_iters, int burn_in, int thin, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <20 MB (chain + batch gradient buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`; gradient buffer `alignas(64)`

## Performance Target
- Python baseline: PyTorch mini-batch SGD + noise injection
- Target: ≥4x faster when gradient is precomputed/analytic
- Benchmark: 50k iters × batch sizes {32, 128, 512} × d ∈ {10, 100}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Vectorize weight update.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on gradient and w. Clip gradient norm to prevent blow-up. Use double for step √ε.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG (xoshiro256** or PCG).

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_111.py` | Posterior mean matches full-batch HMC within 10% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than PyTorch reference |
| 5 | `pytest test_edges_meta_111.py` | Degenerate batch, ε_t=0, gradient NaN all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller supplies `grad_minibatch` with batch index
- Optional: reuses RNG utilities from META-106

## Pipeline Stage Non-Conflict
**Owns:** Mini-batch Bayesian posterior sampling for large datasets.
**Alternative to:** META-109 HMC / META-110 NUTS when full-batch gradient is too costly.
**Coexists with:** Full-batch samplers — SGLD activates when `data.n > sgld.threshold`.

## Test Plan
- Bayesian logistic regression on synthetic (n=10k, d=50): mean within 10% of HMC
- Step schedule verification: a=0.1, γ=0.55 produces decreasing ε
- Gradient NaN guard: raises ValueError
- Single mini-batch (full-batch edge case): behaves like Langevin
