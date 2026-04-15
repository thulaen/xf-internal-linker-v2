# META-132 — Proximal Gradient / ISTA

## Overview
**Category:** Advanced gradient optimizer
**Extension file:** `ista.cpp`
**Replaces/improves:** Subgradient descent for L1-regularised weight tuning (sparse feature selection on rerankers)
**Expected speedup:** ≥4x over Python scikit-learn Lasso coordinate descent for dense prox
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: weights x ∈ ℝ^d, smooth part ∇g(x), L1 weight λ, step η
Output: updated weights x_{t+1}

Composite objective: F(x) = g(x) + λ · ‖x‖₁
Update rule (Rockafellar 1976; Daubechies et al. 2004):
    x_{t+1} = prox_{λη·‖·‖₁}( x_t − η · ∇g(x_t) )
            = soft_threshold( x_t − η · ∇g(x_t), λη )

where  soft_threshold(u, τ) = sign(u) · max(|u| − τ, 0)     (elementwise)
```

- **Time complexity:** O(d) per step after gradient is provided
- **Space complexity:** O(d)
- **Convergence:** O(1/t) on convex g with L-Lipschitz gradient (ISTA); FISTA variant achieves O(1/t²)

## C++ Interface (pybind11)

```cpp
// ISTA step: gradient step on smooth g then soft-threshold
void ista_step(
    float* weights, int d,
    const float* gradient_of_g,
    float learning_rate, float l1_weight
);
```

## Memory Budget
- Runtime RAM: <10 MB (weights + gradient buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: in-place

## Performance Target
- Python baseline: numpy `np.sign(u) * np.maximum(np.abs(u) − tau, 0)`
- Target: ≥4x faster via AVX2 branchless soft-threshold
- Benchmark: d ∈ {1024, 16384, 262144}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Exact zero at τ=|u| required for sparsity pattern reproducibility.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_132.py` | Output matches scikit-learn soft_threshold within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than numpy baseline |
| 5 | `pytest test_edges_meta_132.py` | λ=0, |u|=τ exactly, signed zeros all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** L1-proximal weight update
- **Alternative to:** META-128, META-129, META-130, META-131, META-133, META-134 — mutually exclusive as outer optimizer
- **Coexists with:** META-04 coord ascent (unregularised polish), META-143..149 feature encoders

## Test Plan
- L1 regularised least squares: verify converges to scikit-learn Lasso solution
- λ = large: verify full sparsity (all zeros)
- |u| = τ boundary: verify output is exact zero
- d=1: matches scalar soft_threshold
