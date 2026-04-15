# META-122 — Natural Evolution Strategies (NES)

## Overview
**Category:** Evolutionary weight optimizer (natural-gradient population)
**Extension file:** `natural_evolution_strategies.cpp`
**Replaces/improves:** Heuristic ES by following the natural gradient of E_θ[f(x)]
**Expected speedup:** ≥6x over Python reference loop
**RAM:** <25 MB | **Disk:** <1 MB

## Algorithm

```
Input: search distribution π_θ(x) (e.g. N(μ, Σ)), fitness f, learning rate η, pop λ
Output: θ*

for g = 1..G:
    sample x_i ~ π_θ for i = 1..λ
    evaluate f_i = f(x_i)
    # ∇_θ E_θ[f(x)] = E_θ[f(x) · ∇_θ log π_θ(x)] with natural gradient F⁻¹∇
    g_θ ← (1/λ) Σ_i u(f_i) · ∇_θ log π_θ(x_i)     # u = fitness shaping
    F ← (1/λ) Σ_i ∇_θ log π_θ(x_i) ∇_θ log π_θ(x_i)ᵀ   # Fisher info
    θ ← θ + η · F⁻¹ · g_θ
return μ component of θ
```

- **Time complexity:** O(G × λ × (f_eval + d²))
- **Space complexity:** O(θ_dim² + λ × d)
- **Convergence:** Natural-gradient ascent on E[f]; rotation/scale-invariant

## Academic Source
Wierstra D., Schaul T., Glasmachers T., Sun Y., Peters J., Schmidhuber J. "Natural Evolution Strategies." *Journal of Machine Learning Research* 15:949–980, 2014. URL: https://jmlr.org/papers/v15/wierstra14a.html.

## C++ Interface (pybind11)

```cpp
// xNES / sNES variant with diagonal/full covariance
std::vector<float> nes_optimize(
    const float* initial_mu, int d,
    std::function<float(const float*)> fitness,
    int population_lambda, float learning_rate_mu, float learning_rate_sigma,
    bool full_cov, int n_generations, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <25 MB (λ=200 × d=200 + Σ matrix d×d)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`; Σ stored contiguous `alignas(64)`

## Performance Target
- Python baseline: pure-python NES (as in reference paper)
- Target: ≥6x faster
- Benchmark: λ ∈ {50, 200, 800} × G=500 × d ∈ {10, 50}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Fitness eval may use OpenMP.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on Σ and population arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for Fisher averages. Guard Σ against singularity (add jitter λ·I).

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_122.py` | μ within 3% of PyBrain NES reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_122.py` | λ=2, singular Σ, d=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone). Optionally shares ES utilities with META-121.

## Pipeline Stage Non-Conflict
**Owns:** Natural-gradient search over Gaussian policy distributions.
**Alternative to:** META-121 1/5-rule ES (NES adapts full Σ automatically).
**Coexists with:** META-120 GA, META-123 tabu — selected by `optimizer.family`.

## Test Plan
- Ill-conditioned quadratic: NES recovers anisotropic Σ
- Sphere d=20: converges within 1000 gens
- Singular Σ guard: verify jitter restores PSD
- Fitness NaN: verify raises ValueError
