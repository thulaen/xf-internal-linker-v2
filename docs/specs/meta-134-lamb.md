# META-134 — LAMB Optimiser

## Overview
**Category:** Advanced gradient optimizer (layer-wise adaptive)
**Extension file:** `lamb.cpp`
**Replaces/improves:** Adam on large-batch weight tuning where layer-wise trust ratios matter
**Expected speedup:** ≥3x over Python reference
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

```
Input: weights w ∈ ℝ^d grouped into L layers, gradient g_t, β₁=0.9, β₂=0.999
State: Adam moments m, v per parameter
Output: updated w_{t+1}

Update rule (You et al., ICLR 2020):
    m_t = β₁·m_{t-1} + (1−β₁)·g_t
    v_t = β₂·v_{t-1} + (1−β₂)·g_t²
    r_t = m̂_t / (√(v̂_t) + ε)    + weight_decay · w_t     (Adam update with decoupled WD)
    per layer ℓ:
        trust_ratio_ℓ = ‖w_ℓ‖ / ‖r_ℓ‖           (0 if either norm is 0)
    w_{t+1} = w_t − η · trust_ratio_ℓ · r_t
```

- **Time complexity:** O(d) per step + O(L) norm reductions
- **Space complexity:** O(d) for m, v
- **Convergence:** Scales learning rate across layers; proven convergent in the paper

## C++ Interface (pybind11)

```cpp
// LAMB step with layer-wise trust ratio
void lamb_step(
    float* weights, float* m, float* v,
    const float* gradient,
    const int* layer_offsets, int num_layers, int d,
    float learning_rate, float beta1, float beta2,
    float eps, float weight_decay, int step
);
```

## Memory Budget
- Runtime RAM: <15 MB (m, v buffers + per-layer norms)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: numpy with per-layer norm loop
- Target: ≥3x faster via AVX2 norms + FMA update
- Benchmark: d ∈ {4096, 65536, 524288} across 10 layers

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Trust ratio defined as 0 when ‖w‖=0 or ‖r‖=0.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_134.py` | Output matches PyTorch LAMB within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_134.py` | ‖w‖=0 layer, single-layer case, NaN grad all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Layer-wise adaptive weight update
- **Alternative to:** META-128..133, META-135 — mutually exclusive as outer optimizer
- **Coexists with:** META-04 coord ascent polish, META-136 label smoothing

## Test Plan
- Single-layer network: verify matches Adam with decoupled WD
- Multi-layer: verify different effective step sizes per layer norm
- Zero-norm layer: verify trust ratio = 0 (no update on that layer)
- Weight decay = 0: verify equivalence to vanilla LAMB without WD
