# META-142 — Gradient Noise Injection

## Overview
**Category:** Regularisation / noise
**Extension file:** `grad_noise.cpp`
**Replaces/improves:** Plain gradient updates when training is stuck in saddle / poor local minima
**Expected speedup:** ≥4x over Python numpy add-noise loop
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: gradient g_t ∈ ℝ^d, step t, base η, decay γ
Output: noisy gradient g̃_t

Rule (Neelakantan et al., arXiv:1511.06807, 2015):
    σ_t² = η / (1 + t)^γ                     (γ ∈ [0,1], typical γ=0.55)
    ξ_t ~ N(0, σ_t² · I)
    g̃_t = g_t + ξ_t
```

- **Time complexity:** O(d) per step
- **Space complexity:** O(d) scratch or in-place
- **Convergence:** Asymptotic σ_t² → 0 preserves convergence; empirically escapes saddle points

## C++ Interface (pybind11)

```cpp
// Add time-decaying Gaussian noise to a gradient vector in place
void grad_noise_step(
    float* gradient, int d,
    float eta, float gamma, int step,
    uint64_t rng_seed
);
```

## Memory Budget
- Runtime RAM: <10 MB (gradient + RNG state)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned; in place

## Performance Target
- Python baseline: numpy `np.random.normal(0, sigma, d) + g`
- Target: ≥4x faster via SIMD Ziggurat or Box-Muller Gaussian
- Benchmark: d ∈ {1024, 16384, 262144}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. σ_t computed with floor to avoid underflow at large t.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_142.py` | Distribution mean/var match expected within 2 sigma |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than numpy baseline |
| 5 | `pytest test_edges_meta_142.py` | η=0 (no-op), γ=0 (constant σ), step=0 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained PRNG)

## Pipeline Stage Non-Conflict
- **Owns:** Additive Gaussian perturbation of the gradient vector
- **Alternative to:** None — strictly additive; may be combined with any optimizer
- **Coexists with:** All optimizers META-128..135, regularisers META-136..141

## Test Plan
- η=0: g̃_t == g_t bit-exact
- Empirical variance of ξ_t across many samples matches σ_t² within 5%
- Large t (e.g. t=10⁶): σ_t close to but above zero
- Multiple calls with same seed, same step: reproducible
