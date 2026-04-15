# META-116 — Stein Variational Gradient Descent (SVGD)

## Overview
**Category:** Particle-based variational posterior approximator
**Extension file:** `svgd.cpp`
**Replaces/improves:** MCMC when smooth deterministic particle updates are preferred
**Expected speedup:** ≥6x over PyTorch SVGD loop
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

```
Input: initial particles {w_i^{(0)}}_{i=1..n}, target ∇log p(w), kernel k, step ε, T iters
Output: {w_i^{(T)}} approximating samples from p

for t = 0..T-1:
    # w^{(t+1)} = w^{(t)} + ε · φ*(w^{(t)}) with
    #   φ*(w) = (1/n) · Σ_j [ k(w_j, w) · ∇_j log p(w_j) + ∇_j k(w_j, w) ]
    compute kernel matrix K_ij = k(w_i, w_j)
    compute score g_j = ∇log p(w_j)
    for i = 1..n:
        φ_i ← (1/n) · Σ_j [K_ij · g_j + ∇_j K_ij]
    w_i ← w_i + ε · φ_i
return {w_i}
```

- **Time complexity:** O(T × n² × d)
- **Space complexity:** O(n × d + n²)
- **Convergence:** Descends KL(q_t || p) in RKHS; no stochasticity at particle level

## Academic Source
Liu Q., Wang D. "Stein Variational Gradient Descent: A General Purpose Bayesian Inference Algorithm." *Advances in Neural Information Processing Systems 29 (NeurIPS 2016)*. URL: https://proceedings.neurips.cc/paper/2016/hash/b3ba8f1bee1238a2f37603d90b58898d-Abstract.html.

## C++ Interface (pybind11)

```cpp
// SVGD with RBF kernel and adaptive bandwidth (median heuristic)
std::vector<std::vector<float>> svgd(
    const float* initial_particles, int n, int d,
    std::function<void(const float*, float*)> score_fn,   // ∇log p
    float step_eps, int n_iters, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <30 MB (n=1000 particles × d=200 + n² kernel matrix)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: contiguous particle arena `alignas(64)`; kernel matrix `alignas(64)`

## Performance Target
- Python baseline: PyTorch SVGD with autograd
- Target: ≥6x faster for analytic score
- Benchmark: n ∈ {100, 500, 2000} × d ∈ {10, 50} × T=1000

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Kernel matrix build may use OpenMP.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Kernel matrix sized `n×n` — cap n≤5000.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on particle and kernel buffers. Vectorize pairwise distance.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on particles and score. Double accumulator for bandwidth median.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_116.py` | Final particle moments match reference within 5% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than PyTorch reference |
| 5 | `pytest test_edges_meta_116.py` | n=2, identical init, zero score handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Requires analytic score ∇log p

## Pipeline Stage Non-Conflict
**Owns:** Deterministic particle-based posterior approximation.
**Alternative to:** META-113 SMC (deterministic vs. stochastic).
**Coexists with:** META-114 / META-117 VI — SVGD is particle-form VI.

## Test Plan
- 2D Gaussian target: particle mean/var match within 5% after 500 iters
- Bimodal target: verify both modes covered with RBF bandwidth
- n=2 edge: reduces to pairwise attraction/repulsion
- NaN score: verify raises ValueError
