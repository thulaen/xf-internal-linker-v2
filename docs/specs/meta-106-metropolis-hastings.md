# META-106 — Metropolis-Hastings Sampler

## Overview
**Category:** MCMC weight posterior sampler
**Extension file:** `metropolis_hastings.cpp`
**Replaces/improves:** Point-estimate weight tuning in `recommended_weights.py` with full posterior sampling
**Expected speedup:** ≥8x over Python `numpy`/`scipy.stats` proposal loop
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm

```
Input: target log-density log π(w), proposal q(·|w), initial w_0, n_samples, burn_in
Output: chain {w_t} approximating samples from π

w ← w_0
for t = 1..n_samples + burn_in:
    # propose w' ~ q(·|w), accept with α = min(1, π(w')·q(w|w') / (π(w)·q(w'|w)))
    w' ← sample_proposal(q, w)
    log_α ← log π(w') + log q(w|w') - log π(w) - log q(w'|w)
    if log(U(0,1)) < log_α:
        w ← w'
    if t > burn_in:
        append w to chain
```

- **Time complexity:** O((n_samples + burn_in) × eval_cost)
- **Space complexity:** O(n_samples × d) for chain
- **Convergence:** Detailed balance ensures stationary distribution = π; mixing depends on proposal scale

## Academic Source
Metropolis N. et al. "Equation of State Calculations by Fast Computing Machines." *J. Chem. Phys.* 21(6):1087–1092, 1953. DOI: 10.1063/1.1699114.
Hastings W.K. "Monte Carlo sampling methods using Markov chains and their applications." *Biometrika* 57(1):97–109, 1970. DOI: 10.1093/biomet/57.1.97.

## C++ Interface (pybind11)

```cpp
// Sample posterior over weights via symmetric/asymmetric MH
std::vector<std::vector<float>> metropolis_hastings(
    const float* initial_w, int d,
    std::function<float(const float*)> log_target,
    std::function<void(const float*, float*)> propose,
    std::function<float(const float*, const float*)> log_q_ratio,
    int n_samples, int burn_in, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <12 MB (chain + working state)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_samples)`

## Performance Target
- Python baseline: `numpy.random` proposal loop + `scipy.stats` log-pdf
- Target: ≥8x faster (eliminates Python-side RNG + log-pdf overhead)
- Benchmark: 10k samples × 50 dims, 3 input sizes (d=10, 50, 200)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Use log-space for acceptance ratio.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG (xoshiro256** or PCG), not `rand()`.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_106.py` | Chain mean/var matches numpy reference within 3% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_106.py` | Degenerate proposal, NaN target, d=1, n=10 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone sampler)
- Optional: META-07 RNG utility if extracted

## Pipeline Stage Non-Conflict
**Owns:** Posterior sampling for weight uncertainty quantification.
**Alternative to:** META-04 (coord ascent, point estimate) — MH gives full posterior.
**Coexists with:** META-107 Gibbs, META-108 Slice — all MCMC samplers, dispatched by config flag.

## Test Plan
- 1D Gaussian target: chain mean within 0.05, variance within 10%
- Banana (Rosenbrock) density: visual check of scatter vs. reference
- NaN target returns: verify raises ValueError
- Zero-variance proposal: verify chain stays constant (no silent NaN)
