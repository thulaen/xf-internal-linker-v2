# META-128 — Natural Gradient Optimizer

## Overview
**Category:** Advanced gradient optimizer
**Extension file:** `natural_gradient.cpp`
**Replaces/improves:** Vanilla SGD and Adam in weight tuning when the parameter space has non-Euclidean geometry
**Expected speedup:** ≥4x over Python implementation using numpy Fisher inverse
**RAM:** <30 MB | **Disk:** <1 MB

## Algorithm

```
Input: weights w ∈ ℝ^d, gradient ∇L(w), learning rate η, Fisher damping λ
Output: updated weights w_{t+1}

Update rule (Amari 1998):
    w_{t+1} = w_t − η · F⁻¹ · ∇L(w_t)
    where F = E[∇log p(x;w) · ∇log p(x;w)ᵀ]   (Fisher information matrix)

Practical approximation (empirical Fisher with damping):
    F̂ = (1/N) Σ_i g_i · g_iᵀ + λ·I
    Δw = solve(F̂, ∇L(w))   via Cholesky
    w_{t+1} = w_t − η · Δw
```

- **Time complexity:** O(d³) for Cholesky of d×d Fisher; O(d²) per update after factor
- **Space complexity:** O(d²) for Fisher matrix storage
- **Convergence:** Asymptotically second-order efficient (Fisher = asymptotic covariance of MLE)

## C++ Interface (pybind11)

```cpp
// Natural gradient step with empirical Fisher inverse
std::vector<float> natural_gradient_step(
    const float* weights, int d,
    const float* per_sample_grads, int n_samples,
    const float* mean_gradient,
    float learning_rate, float damping
);
```

## Memory Budget
- Runtime RAM: <30 MB (Fisher matrix d² floats for d ≤ 2500)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector<float>` aligned to 64 bytes, `reserve(d*d)`

## Performance Target
- Python baseline: numpy `np.linalg.solve(F, g)` per step
- Target: ≥4x faster via Eigen Cholesky and BLAS
- Benchmark: d ∈ {64, 256, 1024}, N=10000 samples

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Fisher is PSD; damping λ ≥ 1e-4 ensures invertibility.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_128.py` | Output matches numpy reference within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than Python reference |
| 5 | `pytest test_edges_meta_128.py` | Singular Fisher, n=1, NaN/Inf all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Eigen (header-only) for Cholesky decomposition
- Gradient vector from META-04 or upstream optimizer

## Pipeline Stage Non-Conflict
- **Owns:** Fisher-preconditioned gradient step on weight vector
- **Alternative to:** META-129 (AdaBelief), META-133 (Apollo), Adam baseline — mutually exclusive per training run
- **Coexists with:** META-136 (label smoothing), META-04 (coord ascent as final polish)

## Test Plan
- 2D Gaussian MLE: verify faster convergence than vanilla SGD
- Well-conditioned quadratic: verify single-step optimum within tol
- Singular empirical Fisher: verify damping keeps step finite
- NaN in per-sample gradient: verify raises ValueError before Cholesky
