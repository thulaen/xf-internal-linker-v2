# META-119 — Amortised Variational Inference

## Overview
**Category:** Variational posterior approximator (shared parameters across data)
**Extension file:** `amortised_vi.cpp`
**Replaces/improves:** Per-datapoint λ in META-114/117 by sharing neural-net parameters φ
**Expected speedup:** ≥4x over PyTorch encoder forward+backward
**RAM:** <60 MB | **Disk:** <1 MB

## Algorithm

```
Input: dataset {x_n}, encoder f_φ : X → Λ, decoder p_θ(x|z), prior p(z)
Output: φ, θ maximizing Σ_n ELBO(x_n)

# parametrize q_φ(z|x) with neural net, share φ across x
for t = 1..n_iters:
    sample mini-batch B = {x_n}
    for x_n in B:
        λ_n ← f_φ(x_n)
        ε ~ p(ε),  z_n ← g(ε, λ_n)
        L_n ← log p_θ(x_n | z_n) − KL(q_φ(z|x_n) || p(z))
    g_φ ← ∇_φ (1/|B|) Σ L_n
    g_θ ← ∇_θ (1/|B|) Σ L_n
    φ ← φ + γ · g_φ;  θ ← θ + γ · g_θ
return φ, θ
```

- **Time complexity:** O(n_iters × |B| × (encoder_fwd + decoder_fwd))
- **Space complexity:** O(|φ| + |θ| + |B| × z_dim)
- **Convergence:** Stochastic gradient ascent on averaged ELBO; convergence same as SGD

## Academic Source
Gershman S.J., Goodman N.D. "Amortized inference in probabilistic reasoning." *Proceedings of the 36th Annual Conference of the Cognitive Science Society (CogSci 2014)*, pp. 517–522. URL: https://cogsci.mindmodeling.org/2014/papers/143/.

## C++ Interface (pybind11)

```cpp
// Amortised VI loop; encoder/decoder supplied as forward/backward callbacks
std::pair<std::vector<float>, std::vector<float>> amortised_vi(
    const float* initial_phi, int phi_dim,
    const float* initial_theta, int theta_dim,
    std::function<void(const float*, const float*, float*)> encoder_fwd,     // x, φ → λ
    std::function<void(const float*, const float*, const float*, float*)> elbo_grad,  // → (g_φ, g_θ)
    const float* data_x, int n_data, int x_dim,
    int batch_size, int n_iters, float lr, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <60 MB (φ, θ, batch buffers; scales with |φ|)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve`; batch arena `alignas(64)`

## Performance Target
- Python baseline: PyTorch VAE-style loop
- Target: ≥4x faster when encoder/decoder are analytic
- Benchmark: |B| ∈ {32, 128, 512} × n_iters=10k × (x_dim, z_dim) ∈ {(784,20), (100,10)}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Batch parallel inference may use OpenMP.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on φ, θ, and batch buffers.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on φ, θ. Double accumulator for batch ELBO average. Gradient clipping.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_119.py` | Final ELBO within 2% of PyTorch VAE reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than PyTorch reference |
| 5 | `pytest test_edges_meta_119.py` | |B|=1, n_data=|B|, NaN data all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Composes with META-118 reparam VI (standard pairing for VAE)
- Caller supplies encoder/decoder forward + gradient callbacks

## Pipeline Stage Non-Conflict
**Owns:** Single-shot posterior q(z|x) via shared encoder.
**Alternative to:** Per-datapoint VI (META-114/117/118) when dataset is large.
**Coexists with:** Any sample-based decoder; commonly paired with META-118.

## Test Plan
- VAE on synthetic mixture: recovered modes match generator within 5%
- Generalization: held-out ELBO within 3% of training ELBO
- |B|=1: convergence slower but bounded
- NaN input data: verify raises ValueError
