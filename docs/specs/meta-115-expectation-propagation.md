# META-115 — Expectation Propagation (EP)

## Overview
**Category:** Variational posterior approximator (moment matching)
**Extension file:** `expectation_propagation.cpp`
**Replaces/improves:** Mean-field VI when marginals need correlation capture
**Expected speedup:** ≥5x over Python site-update loop
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: factorized target p(z) ∝ Π f_i(z), Gaussian q(z), n_sites n
Output: q(z) ≈ p(z) via moment matching

initialize site approximations {f̃_i(z) = N(μ_i, Σ_i)}
q(z) ← Π f̃_i
# iteratively replace factor f_i with Gaussian approximation matching expectations
repeat:
    for i = 1..n:
        q_{-i}(z) ∝ q(z) / f̃_i(z)                      # cavity
        q_new_i(z) ∝ q_{-i}(z) · f_i(z)                 # tilted
        f̃_i ← moment_match(q_new_i) / q_{-i}            # new site
        q ← q_{-i} · f̃_i
until site changes < tol
return q
```

- **Time complexity:** O(iters × n × moment_match_cost)
- **Space complexity:** O(n × site_param_dim + q_dim²)
- **Convergence:** Not guaranteed (can oscillate); damping often required

## Academic Source
Minka T.P. "Expectation Propagation for approximate Bayesian inference." *Proceedings of UAI 2001*, pp. 362–369. URL: https://tminka.github.io/papers/ep/ (arXiv: cs.AI/0212002).

## C++ Interface (pybind11)

```cpp
// EP with optional damping α ∈ (0,1]
std::pair<std::vector<float>, std::vector<float>> ep_fit(
    int n_sites, int d,
    std::function<void(int, const float*, const float*, float*, float*)> tilted_moments,
    float damping, int max_iters, float tol
);
```

## Memory Budget
- Runtime RAM: <20 MB (site params + cavity + tilted buffers)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`; site store `alignas(64)`

## Performance Target
- Python baseline: GPML-style EP in numpy
- Target: ≥5x faster
- Benchmark: n ∈ {100, 1k, 10k} × d ∈ {5, 50}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on site buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for variance reductions. Guard against negative site precision via projection.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. Cavity with negative precision flagged and damped.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_115.py` | Moments match GPML reference within 2% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than Python reference |
| 5 | `pytest test_edges_meta_115.py` | Negative cavity precision, oscillation, n=1 pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller supplies `tilted_moments` for factor-specific moment matching

## Pipeline Stage Non-Conflict
**Owns:** Gaussian-family posterior approximation for sums of local factors.
**Alternative to:** META-114 mean-field VI when cross-factor correlations matter.
**Coexists with:** META-114, META-117 — selected by `vi.family` flag.

## Test Plan
- Probit regression: marginal variances within 2% of MCMC reference
- Damping α=0.5 stabilizes oscillating case
- n=1: reduces to single-site projection
- Negative cavity handling: verify auto-damping kicks in
