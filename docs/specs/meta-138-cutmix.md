# META-138 — CutMix

## Overview
**Category:** Regularisation / noise (data augmentation)
**Extension file:** `cutmix.cpp`
**Replaces/improves:** Mixup where locality of features matters (spatial-aware inputs)
**Expected speedup:** ≥3x over Python reference
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: batch X ∈ ℝ^{N×H×W×C}, targets Y ∈ ℝ^{N×K}, β > 0
Output: (X̃, Ỹ)

Rule (Yun et al., ICCV 2019):
    λ ~ Beta(β, β)
    for each sample i, pair j:
        box M of area (1−λ)·H·W with random centre
        X̃_i = X_i with region M replaced by X_j[M]
    λ_adjusted = 1 − |M| / (H·W)        (actual fraction kept from X_i)
    Ỹ_i = λ_adjusted · Y_i + (1 − λ_adjusted) · Y_j
```

- **Time complexity:** O(N·H·W·C) for copy + mask
- **Space complexity:** O(N·H·W·C) for X̃
- **Convergence:** Discrete patch mix — yields sharper attributions than Mixup

## C++ Interface (pybind11)

```cpp
// CutMix one batch
void cutmix_batch(
    float* X_mixed, float* Y_mixed,
    const float* X, const float* Y,
    const int* permutation,
    int N, int H, int W, int C, int K,
    float beta, uint64_t rng_seed
);
```

## Memory Budget
- Runtime RAM: <20 MB (output tensors)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: numpy with boolean mask copy
- Target: ≥3x faster via AVX2 memcpy of rows inside box
- Benchmark: N∈{32, 256}, H=W=64, C=3

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Box bounds clamped inside [0,H)×[0,W).

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Recompute λ_adjusted from actual box area — do not trust sampled λ.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_138.py` | Output matches numpy reference within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_138.py` | Zero-area box, full-area box, H=W=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained PRNG)

## Pipeline Stage Non-Conflict
- **Owns:** Rectangular patch-replacement augmentation
- **Alternative to:** META-137 (Mixup), META-139 (Cutout) — mutually exclusive per batch
- **Coexists with:** All optimizers META-128..135, META-136 label smoothing

## Test Plan
- Box fraction matches 1 − λ_adjusted within 1e-6
- Identity permutation: patch-from-self → X̃ = X
- β very large: λ ≈ 0.5 average box-kept fraction
- Sum of target row Σ_k Ỹ_{i,k} = 1 preserved
