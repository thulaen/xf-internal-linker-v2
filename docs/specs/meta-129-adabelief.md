# META-129 — AdaBelief Optimizer

## Overview
**Category:** Advanced gradient optimizer
**Extension file:** `adabelief.cpp`
**Replaces/improves:** Adam where gradient surprise is a better curvature proxy than raw squared gradient
**Expected speedup:** ≥3x over Python/numpy Adam loop
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: weights w ∈ ℝ^d, gradient g_t, β₁=0.9, β₂=0.999, ε=1e-8
State: first moment m, belief variance s
Output: updated weights w_{t+1}

Update rule (Zhuang et al., NeurIPS 2020):
    m_t = β₁·m_{t-1} + (1−β₁)·g_t
    s_t = β₂·s_{t-1} + (1−β₂)·(g_t − m_t)²   + ε
    m̂_t = m_t / (1 − β₁^t)
    ŝ_t = s_t / (1 − β₂^t)
    w_{t+1} = w_t − η · m̂_t / (√(ŝ_t) + ε)
```

- **Time complexity:** O(d) per step
- **Space complexity:** O(d) for m, s
- **Convergence:** Same regret bound as Adam; empirically faster on noisy landscapes

## C++ Interface (pybind11)

```cpp
// AdaBelief one-step update with bias correction
void adabelief_step(
    float* weights, float* m, float* s, int d,
    const float* gradient,
    float learning_rate, float beta1, float beta2,
    float eps, int step
);
```

## Memory Budget
- Runtime RAM: <10 MB (3 × d floats: w, m, s)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned buffers; extension only reads/writes in place

## Performance Target
- Python baseline: numpy vectorised Adam loop
- Target: ≥3x faster via AVX2 fused multiply-add
- Benchmark: d ∈ {1024, 16384, 262144}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Bias-correction denominators clamped away from zero at step=0.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_129.py` | Output matches PyTorch AdaBelief within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_129.py` | step=0, zero gradient, large d all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained optimizer state)

## Pipeline Stage Non-Conflict
- **Owns:** First-moment + belief-variance update for weight vector
- **Alternative to:** META-128 (natural gradient), META-133 (Apollo), META-134 (LAMB), Adam baseline — mutually exclusive per run
- **Coexists with:** META-04 (coord ascent), gradient-noise injection META-142

## Test Plan
- Rosenbrock: converges within 2000 steps
- Constant gradient: verify m_t → g, s_t → ε (belief = 0)
- Zero gradient after spike: verify rapid decay of effective step
- Dimension d=1: matches scalar reference implementation
