# META-110 — No-U-Turn Sampler (NUTS)

## Overview
**Category:** MCMC weight posterior sampler (adaptive HMC)
**Extension file:** `nuts.cpp`
**Replaces/improves:** META-109 HMC by adapting leapfrog count L automatically
**Expected speedup:** ≥8x over PyMC NUTS (pure-C++ tree build vs. Python recursion)
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: potential U(q), gradient ∇U, step ε, max_depth, n_samples
Output: chain {q_t} with stationary distribution π

for t = 1..n_samples:
    p ← N(0, M)
    u ← U(0, exp(-H(q, p)))              # slice variable
    (q⁻, q⁺, p⁻, p⁺, q_cand, n, s) ← (q, q, p, p, q, 1, 1)
    j ← 0
    # recursively build tree of leapfrog states until U-turn criterion
    #   (q⁺ - q⁻)·p⁺ < 0  or  (q⁺ - q⁻)·p⁻ < 0
    while s = 1 and j < max_depth:
        direction ← ±1 with prob 1/2
        # doubling step: extend tree from (q⁻, p⁻) or (q⁺, p⁺)
        (extend tree by 2^j leapfrog steps in direction)
        if subtree_s = 1:
            with prob n'/n, q_cand ← subtree q_cand
        n ← n + n'
        s ← s · subtree_s · 1[(q⁺ - q⁻)·p⁻ ≥ 0] · 1[(q⁺ - q⁻)·p⁺ ≥ 0]
        j ← j + 1
    q ← q_cand
    append q to chain
```

- **Time complexity:** O(n_samples × 2^avg_depth × grad_eval_cost)
- **Space complexity:** O(n_samples × d + 2^max_depth for tree)
- **Convergence:** No-U-turn criterion prevents wasted gradient evals; detailed balance preserved

## Academic Source
Hoffman M.D., Gelman A. "The No-U-Turn Sampler: Adaptively Setting Path Lengths in Hamiltonian Monte Carlo." *Journal of Machine Learning Research* 15:1593–1623, 2014. URL: https://jmlr.org/papers/v15/hoffman14a.html.

## C++ Interface (pybind11)

```cpp
// NUTS with dual-averaging ε adaptation
std::vector<std::vector<float>> nuts_sample(
    const float* initial_q, int d,
    std::function<float(const float*)> U,
    std::function<void(const float*, float*)> grad_U,
    float target_accept, int max_depth,
    int n_samples, int n_warmup, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <20 MB (chain + tree buffers up to 2^max_depth × d)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`; tree uses preallocated arena

## Performance Target
- Python baseline: PyMC NUTS or custom pure-python
- Target: ≥8x faster
- Benchmark: 5k post-warmup samples × d ∈ {10, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA — recursive tree uses explicit stack or preallocated arena. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Cap `max_depth ≤ 12` to bound 2^12 states.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for H reductions. Divergence threshold ΔH > 1e3.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Iterative tree building preferred to recursive for stack safety.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_110.py` | Moments match PyMC within 3% on Gaussian |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than PyMC reference |
| 5 | `pytest test_edges_meta_110.py` | max_depth=1, funnel, divergence path handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Shares leapfrog utilities with META-109 HMC
- Requires analytic gradient

## Pipeline Stage Non-Conflict
**Owns:** Tuning-free HMC via adaptive trajectory length.
**Alternative to:** META-109 HMC (NUTS preferred when L unknown).
**Coexists with:** META-111 SGLD — NUTS for full-batch, SGLD for mini-batch.

## Test Plan
- 8-schools hierarchical model: posterior matches Stan within 3%
- Correlated Gaussian: verify avg tree depth < 8
- Divergent funnel: verify divergence count flagged
- NaN gradient: verify raises ValueError
