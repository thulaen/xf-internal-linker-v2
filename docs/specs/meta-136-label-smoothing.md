# META-136 — Label Smoothing

## Overview
**Category:** Regularisation / noise
**Extension file:** `label_smoothing.cpp`
**Replaces/improves:** Hard-label one-hot cross-entropy when ranking model over-concentrates
**Expected speedup:** ≥4x over Python one-hot + smooth in numpy
**RAM:** <5 MB | **Disk:** <1 MB

## Algorithm

```
Input: class labels y ∈ {0,...,K-1}^N, smoothing ε ∈ [0,1)
Output: smoothed target matrix ỹ ∈ ℝ^{N×K}

Rule (Szegedy et al., CVPR 2016):
    y_smooth[i, k] = (1 − ε) · 1{k == y_i} + ε / K

Loss consumed downstream:
    L = − Σ_i Σ_k y_smooth[i, k] · log p(k | x_i)
```

- **Time complexity:** O(N·K) to materialise — can be fused into loss
- **Space complexity:** O(N·K) if stored; O(1) with fused-loss variant
- **Convergence:** Preserves convexity of cross-entropy; shrinks max-logit over-confidence

## C++ Interface (pybind11)

```cpp
// Fused cross-entropy with label smoothing
float label_smoothed_ce(
    const float* logits, int N, int K,
    const int* labels, float epsilon
);

// Optional: materialise smoothed target
void label_smoothed_targets(
    float* target_out, int N, int K,
    const int* labels, float epsilon
);
```

## Memory Budget
- Runtime RAM: <5 MB (fused path keeps only logits + targets)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: optional output buffer caller-owned

## Performance Target
- Python baseline: numpy one-hot + (1-eps)*y + eps/K, then cross-entropy
- Target: ≥4x faster via fused AVX2 kernel
- Benchmark: N∈{1024, 16384, 262144}, K=10

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate labels in [0, K).

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements. Log-sum-exp used for stable log-softmax.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_136.py` | Output matches PyTorch CrossEntropyLoss(label_smoothing=ε) within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than numpy baseline |
| 5 | `pytest test_edges_meta_136.py` | ε=0 (match hard CE), ε=0.99, label out of range all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone loss)

## Pipeline Stage Non-Conflict
- **Owns:** Smoothed target construction + fused cross-entropy
- **Alternative to:** Hard-label CE, focal loss — mutually exclusive per loss step
- **Coexists with:** All optimizers META-128..135 and feature encoders META-143..150

## Test Plan
- ε=0: loss equals standard CE within 1e-6
- ε=1/K: uniform target; loss = log K for any logits with softmax spread
- Out-of-range label: raises ValueError
- Gradient flows through logits only (targets are constants)
