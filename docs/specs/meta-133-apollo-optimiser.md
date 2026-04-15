# META-133 — Apollo Optimiser

## Overview
**Category:** Advanced gradient optimizer (quasi-Newton)
**Extension file:** `apollo.cpp`
**Replaces/improves:** Adam on large weight vectors where diagonal curvature estimate pays off
**Expected speedup:** ≥3x over Python reference with explicit variance correction
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: weights w ∈ ℝ^d, gradient g_t, step s_t = w_t − w_{t-1}, y_t = g_t − g_{t-1}
State: diagonal approx Hessian B ∈ ℝ^d, momentum m ∈ ℝ^d
Output: updated weights w_{t+1}

Quasi-Newton update (Ma, NeurIPS 2021):
    B_{t+1} = B_t + ((y_t − B_t · s_t) · (y_t − B_t · s_t)ᵀ) / (y_tᵀ · s_t)
    (diagonal restriction: only diagonal entries retained)

Variance-corrected step (avoids rectified denominator pathology in Adam):
    m_t = β · m_{t-1} + (1 − β) · g_t
    d_t = m_t / (|B_{t+1}| + ε)
    w_{t+1} = w_t − η · clip(d_t, −τ, τ)
```

- **Time complexity:** O(d) per step (diagonal only)
- **Space complexity:** O(d) for B, m
- **Convergence:** Matches Adam regret bound; empirically better on vision + NLP

## C++ Interface (pybind11)

```cpp
// Apollo quasi-Newton one-step update
void apollo_step(
    float* weights, float* B, float* momentum,
    const float* gradient, const float* prev_gradient,
    const float* step_delta, int d,
    float learning_rate, float beta, float eps, float clip
);
```

## Memory Budget
- Runtime RAM: <20 MB (w, B, m, prev_grad: 4 × d floats)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: numpy with explicit rank-1 diagonal update
- Target: ≥3x faster via AVX2 fused updates
- Benchmark: d ∈ {1024, 16384, 262144}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Guard y_tᵀ·s_t against zero denominator — skip rank-1 update if below 1e-10.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_133.py` | Output matches reference Apollo within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_133.py` | y·s = 0, step=0 (init), NaN grad all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained state)

## Pipeline Stage Non-Conflict
- **Owns:** Diagonal quasi-Newton weight update
- **Alternative to:** META-128..132, META-134, META-135 — mutually exclusive as outer optimizer
- **Coexists with:** META-04 coord ascent polish, META-142 gradient noise

## Test Plan
- Quadratic convex: verify faster than Adam at equal budget
- Non-PSD curvature: verify absolute-value clipping prevents runaway steps
- Init step=0: verify sensible fallback to momentum-only update
- Dimension d=1 matches scalar reference
