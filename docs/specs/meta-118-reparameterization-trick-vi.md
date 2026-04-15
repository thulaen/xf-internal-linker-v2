# META-118 — Reparameterization-Trick VI

## Overview
**Category:** Variational posterior approximator (pathwise gradient)
**Extension file:** `reparam_vi.cpp`
**Replaces/improves:** META-117 BBVI score-function estimator (lower variance via pathwise gradient)
**Expected speedup:** ≥5x over PyTorch reparam VI for analytic models
**RAM:** <25 MB | **Disk:** <1 MB

## Algorithm

```
Input: reparam function g(ε,λ) s.t. z = g(ε,λ), ε ~ p(ε); log p(x,z); log q(z;λ)
Output: λ maximizing ELBO

for t = 1..n_iters:
    sample ε_s ~ p(ε) for s = 1..S
    # z = g(ε,λ) where ε ~ p(ε); ∇_λ L = E_ε[∇_λ (log p(x,g(ε,λ)) − log q(g(ε,λ);λ))]
    g_hat ← 0
    for s = 1..S:
        z_s ← g(ε_s, λ)
        g_hat += ∇_λ log p(x, z_s) · ∇_λ z_s − ∇_λ log q(z_s; λ)
    g_hat ← g_hat / S
    λ ← λ + γ_t · g_hat
return λ
```

- **Time complexity:** O(n_iters × S × grad_cost)
- **Space complexity:** O(|λ|)
- **Convergence:** Low-variance gradient estimator; convergence matches stochastic gradient ascent guarantees

## Academic Source
Kingma D.P., Welling M. "Auto-Encoding Variational Bayes." *International Conference on Learning Representations (ICLR) 2014*. URL: https://arxiv.org/abs/1312.6114.

## C++ Interface (pybind11)

```cpp
// Reparam-trick VI; caller provides g, ∇_λ log p(x,g), ∇_λ log q(g;λ)
std::vector<float> reparam_vi(
    const float* initial_lambda, int lambda_dim, int z_dim,
    std::function<void(const float*, const float*, float*)> reparam,        // g(ε,λ)
    std::function<void(const float*, const float*, float*)> grad_elbo,      // combined grad
    int n_mc_samples, int n_iters, float lr, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <25 MB (λ + ε buffer + z buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`; ε arena `alignas(64)`

## Performance Target
- Python baseline: PyTorch reparam VI with autograd
- Target: ≥5x faster for analytic gradients
- Benchmark: S ∈ {10, 50, 200} × n_iters=5k × (λ_dim, z_dim) ∈ {(10,10), (100,50)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on gradient and ε buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for MC average over S.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_118.py` | ELBO matches PyTorch reparam within 1% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than PyTorch reference |
| 5 | `pytest test_edges_meta_118.py` | Non-reparameterizable rejected, S=1 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller supplies `reparam` (g) and `grad_elbo`
- Works only when reparameterization g(ε,λ) exists (Gaussian, mixture-of-Gaussians OK)

## Pipeline Stage Non-Conflict
**Owns:** Low-variance gradient VI via pathwise derivatives.
**Alternative to:** META-117 BBVI (reparam has lower estimator variance).
**Coexists with:** META-119 amortised VI (reparam is typically used inside amortized).

## Test Plan
- Gaussian q, Gaussian prior, Gaussian likelihood: closed-form ELBO within 1%
- Estimator variance < score-function estimator on same model
- S=1: still converges, slower
- Non-reparameterizable q (discrete): verify error raised
