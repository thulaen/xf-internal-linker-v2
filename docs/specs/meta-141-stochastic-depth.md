# META-141 — Stochastic Depth

## Overview
**Category:** Regularisation / noise
**Extension file:** `stochastic_depth.cpp`
**Replaces/improves:** Fixed-depth network training in deep rerankers — cheaper training + ensemble effect
**Expected speedup:** N/A (training-time — measured by effective FLOPs saved)
**RAM:** <5 MB | **Disk:** <1 MB

## Algorithm

```
Input: layer index l ∈ {1..L}, survival schedule p_L, minibatch residual block F_l
Output: block output y_l

Rule (Huang et al., ECCV 2016):
    p_l = 1 − (l / L) · (1 − p_L)                   (linear decay from 1 to p_L)
    b_l ~ Bernoulli(p_l)
    y_l = x_{l-1} + b_l · F_l(x_{l-1})              (train)
    y_l = x_{l-1} + p_l · F_l(x_{l-1})              (eval, deterministic)
```

- **Time complexity:** O(1) for mask draw; saves O(block_cost) on dropped layers at training time
- **Space complexity:** O(L) for survival probs
- **Convergence:** Implicit ensemble of networks of varying depth

## C++ Interface (pybind11)

```cpp
// Draw Bernoulli survival for a minibatch of residual blocks
void stochastic_depth_mask(
    uint8_t* b_out, int batch_size,
    float survival_prob, uint64_t rng_seed
);

// Compute per-layer survival prob schedule
std::vector<float> stochastic_depth_schedule(int L, float p_L);
```

## Memory Budget
- Runtime RAM: <5 MB (schedule + mask buffers)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: numpy `np.random.binomial`
- Target: parity with numpy on mask draw; win comes from layer skip at forward time (not a kernel we own)
- Benchmark: L ∈ {10, 50, 200}, batch_size up to 4096

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. p_L clamped into [0,1].

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_141.py` | Schedule matches reference within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | Mask draw ≤ numpy baseline time |
| 5 | `pytest test_edges_meta_141.py` | L=1, p_L=1 (identity), p_L=0 (skip all) all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained PRNG)

## Pipeline Stage Non-Conflict
- **Owns:** Per-layer Bernoulli survival masks
- **Alternative to:** META-140 DropConnect, standard Dropout — mutually exclusive per residual block
- **Coexists with:** All optimizers META-128..135, META-136 label smoothing

## Test Plan
- L=1: schedule returns [1.0]
- Linear schedule correctness: p_l monotonically decreasing from 1 to p_L
- Eval mode yields deterministic scaled outputs
- Many mask draws: empirical mean ≈ p_l within 2 sigma
