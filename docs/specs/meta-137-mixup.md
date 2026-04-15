# META-137 — Mixup

## Overview
**Category:** Regularisation / noise (data augmentation)
**Extension file:** `mixup.cpp`
**Replaces/improves:** Plain minibatch training when ranking model over-fits on exact feature patterns
**Expected speedup:** ≥3x over Python numpy mixer
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: batch features X ∈ ℝ^{N×d}, one-hot targets Y ∈ ℝ^{N×K}, α > 0
Output: mixed batch (X̃, Ỹ)

Rule (Zhang et al., ICLR 2018):
    for each pair (i, j) where j is a random permutation of i:
        λ ~ Beta(α, α)
        x̃_i = λ · x_i + (1 − λ) · x_j
        ỹ_i = λ · y_i + (1 − λ) · y_j
```

- **Time complexity:** O(N·d) per batch
- **Space complexity:** O(N·d) for X̃ and O(N·K) for Ỹ
- **Convergence:** Retains original loss function; adds Vicinal Risk Minimization prior

## C++ Interface (pybind11)

```cpp
// Mixup one batch in place
void mixup_batch(
    float* X_mixed, float* Y_mixed,
    const float* X, const float* Y,
    const int* permutation, int N, int d, int K,
    float alpha, uint64_t rng_seed
);
```

## Memory Budget
- Runtime RAM: <20 MB (output buffers caller-owned)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: caller-owned

## Performance Target
- Python baseline: numpy Beta sample + broadcast blend
- Target: ≥3x faster via AVX2 FMA on blend loop
- Benchmark: N ∈ {256, 4096, 65536}, d=128, K=10

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Permutation indices must be in [0, N).

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Beta sampler returns λ ∈ (0,1) — clamp to avoid degenerate exact 0 or 1.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_137.py` | Output matches numpy reference within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy baseline |
| 5 | `pytest test_edges_meta_137.py` | α=∞ (λ→0.5), α→0 (λ ∈ {0,1}), N=1 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (self-contained PRNG)

## Pipeline Stage Non-Conflict
- **Owns:** Convex-combination batch augmentation of features and targets
- **Alternative to:** META-138 (CutMix), META-139 (Cutout) — mutually exclusive per batch; may be stacked across epochs with care
- **Coexists with:** All optimizers META-128..135, META-136 label smoothing

## Test Plan
- α=1 (uniform): verify mean λ ≈ 0.5 over many samples
- Deterministic seed: verify reproducibility
- Identity permutation: verify X̃ = X and Ỹ = Y exactly
- NaN in X: verify raises ValueError
