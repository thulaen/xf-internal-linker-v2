# META-130 — Nesterov Accelerated Gradient (NAG)

## Overview
**Category:** Advanced gradient optimizer
**Extension file:** `nesterov.cpp`
**Replaces/improves:** Plain momentum SGD in weight tuning where convex O(1/t²) rate is achievable
**Expected speedup:** ≥4x over Python loop implementation
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: weights w ∈ ℝ^d, gradient oracle ∇f, momentum γ, learning rate η
State: velocity v ∈ ℝ^d
Output: updated weights w_{t+1}

Update rule (Nesterov 1983, lookahead form):
    v_{t+1} = γ · v_t − η · ∇f(w_t + γ · v_t)       (gradient at lookahead point)
    w_{t+1} = w_t + v_{t+1}

Convergence rate on smooth convex f with L-Lipschitz gradient:
    f(w_t) − f* ≤ O(1/t²)                             (vs O(1/t) for vanilla GD)
```

- **Time complexity:** O(d) per step + one gradient evaluation at lookahead point
- **Space complexity:** O(d) for v
- **Convergence:** Optimal first-order rate on smooth convex problems

## C++ Interface (pybind11)

```cpp
// NAG one-step update; caller computes gradient at lookahead point w + gamma*v
void nesterov_step(
    float* weights, float* velocity, int d,
    const float* gradient_at_lookahead,
    float learning_rate, float momentum
);

// Helper to compute lookahead point w + gamma*v for caller
std::vector<float> nesterov_lookahead(
    const float* weights, const float* velocity, int d, float momentum
);
```

## Memory Budget
- Runtime RAM: <10 MB (w, v, lookahead buffer)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned buffers

## Performance Target
- Python baseline: numpy loop with explicit add/multiply
- Target: ≥4x faster via AVX2 FMA
- Benchmark: d ∈ {1024, 16384, 262144}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_130.py` | Output matches PyTorch SGD(nesterov=True) within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than numpy baseline |
| 5 | `pytest test_edges_meta_130.py` | γ=0, γ=0.99, zero grad, d=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Lookahead momentum update on weight vector
- **Alternative to:** META-128 (natural gradient), META-129 (AdaBelief), META-133 (Apollo), META-134 (LAMB) — mutually exclusive
- **Coexists with:** META-04 coordinate ascent as polish step, META-136 label smoothing

## Test Plan
- Smooth convex quadratic: verify O(1/t²) rate empirically
- Strongly convex problem: verify faster than GD
- γ=0: reduces to vanilla SGD; match GD reference
- Zero gradient entry: verify no drift
