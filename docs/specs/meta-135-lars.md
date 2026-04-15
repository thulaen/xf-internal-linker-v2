# META-135 — LARS Optimiser

## Overview
**Category:** Advanced gradient optimizer (layer-wise adaptive rate scaling)
**Extension file:** `lars.cpp`
**Replaces/improves:** SGD+momentum on large-batch weight tuning, complementary alternative to LAMB
**Expected speedup:** ≥3x over Python reference
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: weights w ∈ ℝ^d in L layers, gradient ∇, momentum β, weight_decay β_wd, trust η_local
State: velocity v per parameter
Output: updated w_{t+1}

Update rule (You, Gitman, Ginsburg, 2017; arXiv:1708.03888):
    per layer ℓ:
        numerator_ℓ = η_local · ‖w_ℓ‖
        denominator_ℓ = ‖∇_ℓ + β_wd · w_ℓ‖        (local grad including decay)
        local_lr_ℓ = numerator_ℓ / (denominator_ℓ + ε)
    v_{t+1} = β · v_t + η · local_lr_ℓ · (∇ + β_wd · w_t)
    w_{t+1} = w_t − v_{t+1}
```

- **Time complexity:** O(d) per step + O(L) norms
- **Space complexity:** O(d) for v
- **Convergence:** Enables large batch sizes (>8K) without divergence — shown empirically on ImageNet

## C++ Interface (pybind11)

```cpp
// LARS step with layer-wise local learning rate
void lars_step(
    float* weights, float* velocity,
    const float* gradient,
    const int* layer_offsets, int num_layers, int d,
    float learning_rate, float momentum,
    float weight_decay, float eta_local, float eps
);
```

## Memory Budget
- Runtime RAM: <10 MB (v buffer + per-layer norms)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: numpy per-layer norm loop + update
- Target: ≥3x faster via AVX2
- Benchmark: d ∈ {4096, 65536, 524288}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. local_lr clamped to [0, 10] to prevent runaway for tiny-gradient layers.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_135.py` | Output matches reference LARS within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_135.py` | ‖w‖=0, ‖∇‖=0, single layer all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained)

## Pipeline Stage Non-Conflict
- **Owns:** Layer-wise LR-scaled momentum update
- **Alternative to:** META-128..134 — mutually exclusive as outer optimizer
- **Coexists with:** META-04 coord ascent, META-136..149 feature/regularisation helpers

## Test Plan
- Uniform layer norms: local_lr ≈ η_local across layers
- Small-norm layer: verify local_lr damps updates there
- weight_decay=0: verify equivalence to pure momentum
- Numerically verify large-batch convergence on toy logistic regression
