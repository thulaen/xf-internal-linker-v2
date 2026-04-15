# META-139 — Cutout

## Overview
**Category:** Regularisation / noise (data augmentation)
**Extension file:** `cutout.cpp`
**Replaces/improves:** Dropout-on-input when a contiguous region mask is preferred
**Expected speedup:** ≥3x over Python numpy mask
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: batch X ∈ ℝ^{N×H×W×C}, mask size s
Output: masked X̃

Rule (DeVries & Taylor, arXiv:1708.04552, 2017):
    for each sample i:
        pick centre (c_h, c_w) uniformly in [0,H)×[0,W)
        zero out the s×s square centred there (clipped to image bounds)
        X̃_i = X_i ⊙ (1 − mask)
    targets Y unchanged
```

- **Time complexity:** O(N·s²·C)
- **Space complexity:** O(N·H·W·C) for X̃ if out-of-place; in-place possible
- **Convergence:** Preserves loss surface; adds feature-level denoising prior

## C++ Interface (pybind11)

```cpp
// Cutout one batch — masks X in place (or writes to X_out)
void cutout_batch(
    float* X_out,
    const float* X_in,
    int N, int H, int W, int C,
    int mask_size, uint64_t rng_seed
);
```

## Memory Budget
- Runtime RAM: <10 MB (in-place) or <20 MB (out-of-place)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: numpy boolean mask + elementwise multiply
- Target: ≥3x faster via AVX2 zeroing of rows
- Benchmark: N∈{32, 256}, H=W=64, C=3, s=16

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Clip box to image bounds.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Zero fill must be bit-exact 0.0f (not subnormal).

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_139.py` | Output matches numpy reference exactly |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_139.py` | s=0 (no-op), s≥H (whole image blank), s=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained PRNG)

## Pipeline Stage Non-Conflict
- **Owns:** Square-region zero masking on inputs
- **Alternative to:** META-137 (Mixup), META-138 (CutMix) — mutually exclusive on same batch
- **Coexists with:** All optimizers META-128..135, META-136 label smoothing

## Test Plan
- s=0: X̃ = X exactly
- Fixed seed: deterministic mask location
- Mask-area count: exactly min(s, H)·min(s, W) zeroed pixels per channel
- H=W=1, s=1: whole pixel zeroed
