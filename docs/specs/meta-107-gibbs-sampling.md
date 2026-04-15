# META-107 — Gibbs Sampler

## Overview
**Category:** MCMC weight posterior sampler (coordinate-wise)
**Extension file:** `gibbs_sampling.cpp`
**Replaces/improves:** Full-block MH when conditionals are tractable; complements META-106
**Expected speedup:** ≥6x over Python per-coordinate conditional sampling loop
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: initial w_0 ∈ ℝ^d, conditionals {p(w_i | w_{-i})}_{i=1..d}, n_samples, burn_in
Output: chain {w_t} with stationary distribution π(w)

w ← w_0
for t = 1..n_samples + burn_in:
    # for each i in 1..d, sample w_i ~ p(w_i | w_{-i})
    for i = 1..d:
        w_i ← sample_conditional(i, w_{-i})
    if t > burn_in:
        append w to chain
```

- **Time complexity:** O((n_samples + burn_in) × d × conditional_eval_cost)
- **Space complexity:** O(n_samples × d)
- **Convergence:** Detailed balance satisfied; mixing fast when conditionals well-separated

## Academic Source
Geman S., Geman D. "Stochastic Relaxation, Gibbs Distributions, and the Bayesian Restoration of Images." *IEEE Transactions on Pattern Analysis and Machine Intelligence* PAMI-6(6):721–741, 1984. DOI: 10.1109/TPAMI.1984.4767596.

## C++ Interface (pybind11)

```cpp
// Gibbs sampler with user-supplied conditional samplers
std::vector<std::vector<float>> gibbs_sample(
    const float* initial_w, int d,
    std::function<float(int, const float*)> sample_conditional,
    int n_samples, int burn_in, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <10 MB (chain + d-dim working state)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_samples)`

## Performance Target
- Python baseline: per-coordinate `scipy.stats` conditional sampling
- Target: ≥6x faster
- Benchmark: 10k iterations × d ∈ {10, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG (xoshiro256** or PCG), not `rand()`.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_107.py` | Marginals match numpy reference within 3% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_107.py` | d=1, correlated conditionals, NaN guard all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone). Conditional samplers supplied by caller.

## Pipeline Stage Non-Conflict
**Owns:** Coordinate-wise conditional posterior sampling.
**Alternative to:** META-106 MH when conditionals are tractable (faster mixing per CPU-second).
**Coexists with:** META-108 Slice, META-113 SMC — chosen by config flag `mcmc.kernel`.

## Test Plan
- Bivariate normal with ρ=0.9: marginals within 5%, correlation within 0.05
- Independent product: verify coordinates uncorrelated in chain
- Single coordinate (d=1): verify identical to direct sampling
- NaN in conditional output: verify raises ValueError
