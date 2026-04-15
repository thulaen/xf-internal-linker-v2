# META-121 — Evolution Strategies (ES)

## Overview
**Category:** Evolutionary weight optimizer (continuous, Gaussian perturbation)
**Extension file:** `evolution_strategies.cpp`
**Replaces/improves:** GA for continuous domains; simpler than CMA-ES, fewer tuning knobs
**Expected speedup:** ≥7x over Python reference loop
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: initial x ∈ ℝ^d, σ ∈ ℝ_+, fitness f (minimizing)
Output: x*

# (1+1): propose x' = x + σ·ε where ε ~ N(0,I); accept if f(x') < f(x)
# σ adapts via Rechenberg's 1/5 success rule
success_count ← 0
for g = 1..G:
    ε ← N(0, I_d)
    x' ← x + σ·ε
    if f(x') < f(x):
        x ← x'; success_count += 1
    if g % window == 0:
        p_s ← success_count / window
        if p_s > 1/5: σ ← σ · c_up
        elif p_s < 1/5: σ ← σ · c_down
        success_count ← 0
    track best

# Optional (μ/ρ+λ): sample λ offspring, select best μ, recombine
```

- **Time complexity:** O(G × f_eval_cost) for (1+1); O(G × λ × f_eval_cost) for (μ/ρ+λ)
- **Space complexity:** O(d) (1+1) or O(λ × d) (population variant)
- **Convergence:** 1/5 rule maintains ~20% success; σ decreases asymptotically near optima

## Academic Source
Rechenberg I. *Evolutionsstrategie: Optimierung technischer Systeme nach Prinzipien der biologischen Evolution.* Frommann-Holzboog, Stuttgart, 1973. ISBN: 978-3-7728-0374-3.

## C++ Interface (pybind11)

```cpp
// (1+1)-ES with Rechenberg 1/5 success rule; returns best x found
std::vector<float> evolution_strategies_1plus1(
    const float* initial_x, int d,
    std::function<float(const float*)> fitness,
    float initial_sigma, int adaptation_window,
    float c_up, float c_down, int n_generations, uint64_t seed
);

// (μ/ρ+λ) variant with recombination
std::vector<float> evolution_strategies_mu_lambda(
    const float* initial_x, int d,
    std::function<float(const float*)> fitness,
    int mu, int rho, int lambda, float sigma_init,
    int n_generations, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <20 MB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`

## Performance Target
- Python baseline: numpy ES loop
- Target: ≥7x faster
- Benchmark: G ∈ {1k, 10k, 100k} × d ∈ {10, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on x and ε buffers. Vectorize `x + σ·ε`.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Guard σ against underflow (clamp ≥ 1e-12).

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_121.py` | Success-rate convergence matches reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_121.py` | σ underflow, d=1, constant fitness handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
**Owns:** Continuous evolution via Gaussian mutation.
**Alternative to:** META-120 GA for continuous weight spaces.
**Coexists with:** META-122 NES — NES replaces 1/5 rule with natural gradient.

## Test Plan
- Sphere d=10: converges to origin within 1e-4
- Rosenbrock d=5: reaches f < 10 within 10k evals
- σ underflow handled: clamps and issues warning
- Fitness NaN: verify raises ValueError
