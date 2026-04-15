# META-109 — Hamiltonian Monte Carlo (HMC)

## Overview
**Category:** MCMC weight posterior sampler (gradient-based)
**Extension file:** `hmc.cpp`
**Replaces/improves:** Random-walk MH when ∇log π(w) is available; exploits gradient for faster mixing
**Expected speedup:** ≥10x over Python leapfrog loop (autograd overhead is the bottleneck)
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

```
Input: potential U(q) = -log π(q), gradient ∇U, step ε, leapfrog L, n_samples
Output: chain {q_t} with stationary distribution π

for t = 1..n_samples:
    p ← N(0, M)                              # resample momentum
    (q', p') ← (q, p)
    # leapfrog: p_{t+1/2} = p_t - (ε/2)·∇U(q_t)
    #          q_{t+1}   = q_t + ε·p_{t+1/2}
    #          p_{t+1}   = p_{t+1/2} - (ε/2)·∇U(q_{t+1})
    for l = 1..L:
        p' ← p' - (ε/2)·∇U(q')
        q' ← q' + ε·M⁻¹·p'
        p' ← p' - (ε/2)·∇U(q')
    # accept via Metropolis
    ΔH ← U(q') + (1/2) p'ᵀM⁻¹p' - U(q) - (1/2) pᵀM⁻¹p
    if log(U(0,1)) < -ΔH: q ← q'
    append q to chain
```

- **Time complexity:** O(n_samples × L × grad_eval_cost)
- **Space complexity:** O(n_samples × d)
- **Convergence:** Symplectic integrator preserves volume; detailed balance via MH step

## Academic Source
Duane S., Kennedy A.D., Pendleton B.J., Roweth D. "Hybrid Monte Carlo." *Physics Letters B* 195(2):216–222, 1987. DOI: 10.1016/0370-2693(87)91197-X.

## C++ Interface (pybind11)

```cpp
// HMC with user-supplied potential and gradient, diagonal mass matrix
std::vector<std::vector<float>> hmc_sample(
    const float* initial_q, int d,
    std::function<float(const float*)> U,
    std::function<void(const float*, float*)> grad_U,
    const float* inv_mass, float step_eps, int n_leapfrog,
    int n_samples, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <15 MB (chain + momentum + gradient buffers)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_samples)`; gradient buffer `alignas(64)`

## Performance Target
- Python baseline: numpy leapfrog + jax/autograd gradient
- Target: ≥10x faster for analytic gradients
- Benchmark: 5k samples × L ∈ {10, 50, 100} × d ∈ {10, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. Vectorize leapfrog inner update.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on q and ∇U. Double accumulator for Hamiltonian difference. Reject steps where ΔH > 1e3 as divergent.

**Performance:** No `std::endl` loops. No `std::function` hot loops (pass function pointer or template). No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_109.py` | Chain mean/var matches PyMC reference within 3% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python reference |
| 5 | `pytest test_edges_meta_109.py` | Divergent trajectory, ε=0, NaN gradient handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Requires analytic gradient (no AD dependency in C++)
- Optional: META-110 NUTS extends HMC for tuning-free L

## Pipeline Stage Non-Conflict
**Owns:** Gradient-based posterior sampling for smooth densities.
**Alternative to:** META-106 MH when gradient is available.
**Coexists with:** META-110 NUTS, META-111 SGLD — all gradient samplers, selected by config.

## Test Plan
- 2D Gaussian with known Σ: verify E[q qᵀ] matches Σ within 5%
- Funnel density (Neal's): verify divergence detection flags reparameterization need
- d=1, L=1: verify reduces to MALA-like step
- NaN gradient: verify raises ValueError
