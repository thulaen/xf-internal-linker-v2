# META-222 — Focal-Loss Calibration

## Overview
**Category:** In-training calibration (loss function)
**Extension file:** `focal_loss.cpp`
**Replaces/improves:** Plain binary cross-entropy in `ranker_training.py`
**Expected speedup:** ≥3x over Python/NumPy loss + gradient loop
**RAM:** <5 MB | **Disk:** <1 MB

## Algorithm

Focal loss down-weights well-classified examples and yields naturally calibrated outputs (Mukhoti et al. NeurIPS 2020).

```
Input: predicted probabilities p ∈ (0,1)^n, binary labels y ∈ {0,1}^n, focusing γ ≥ 0
Output: per-example loss L_i and gradient ∂L/∂p_i

Loss:
  L_focal(p, y) = − (1 − p_t)^γ · log(p_t)
  where p_t = p       if y = 1
             1 − p    if y = 0

Gradient w.r.t. p (used for training):
  ∂L/∂p = − y · γ(1−p)^{γ−1} · log(p) · (−1) − y · (1−p)^γ / p
          − (1−y) · γ·p^{γ−1} · log(1−p)     − (1−y) · p^γ · (−1)/(1−p)

γ = 0 → standard BCE; γ = 2 → paper default; γ = 3 → stronger calibration
```

- **Time complexity:** O(n) forward + O(n) backward
- **Space complexity:** O(n) for losses + gradients
- **Convergence:** Convex in logit space for γ ≤ 1; non-convex but well-behaved for larger γ

## C++ Interface (pybind11)

```cpp
// Compute focal loss and gradient for a batch of predictions
struct FocalOut { std::vector<float> loss, grad; };

FocalOut focal_loss_forward_backward(
    const float* probs, const int* labels, int n,
    float gamma, float eps_clip
);
```

## Memory Budget
- Runtime RAM: <5 MB (loss + grad buffers)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n)`

## Performance Target
- Python baseline: vectorized NumPy forward + backward
- Target: ≥3x faster (fused forward/backward loop, AVX2 `std::pow` via Taylor for small γ)
- Benchmark: n ∈ {1k, 10k, 100k} predictions × γ ∈ {1, 2, 3}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Clip `p ∈ [eps, 1−eps]` before `log`. Double accumulator for total loss.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_222.py` | Loss and grad match PyTorch within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than NumPy reference |
| 5 | `pytest test_edges_meta_222.py` | p=0, p=1, γ=0, γ=5, NaN clipped correctly |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance + gradient-check numeric parity |

## Dependencies
- Training-loop integration in `ranker_training.py` (optional swap for BCE)

## Pipeline Stage & Non-Conflict
- **Stage:** Training-time loss (in-training calibration, no post-hoc fit needed)
- **Owns:** Loss + gradient for focal objective during model fit
- **Alternative to:** Standard BCE + post-hoc calibration (META-219/220/221)
- **Coexists with:** Any post-hoc calibrator as a safety net; reliability diagrams (META-216)

## Test Plan
- γ=0 reduces to BCE: verify bit-exact match to log-loss reference
- Gradient check: verify analytic grad matches finite-diff within 1e-4
- Highly confident correct (p=0.99, y=1): verify loss < BCE equivalent
- Calibration after training: verify ECE improves vs BCE baseline on held-out set
