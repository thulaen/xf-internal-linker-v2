# META-215 — Batch Normalisation (BatchNorm)

## Overview
**Category:** Activation normalisation (cross-sample batch statistics)
**Extension file:** `batch_norm.cpp`
**Replaces/improves:** `torch.nn.functional.batch_norm` CPU path for MLP ranker training-time normalisation
**Expected speedup:** ≥4x over PyTorch CPU at typical hidden dims
**RAM:** <40 MB for batch=1024, H=1024 | **Disk:** <1 MB

## Algorithm

```
Input:  x ∈ ℝ^{B × H}, γ, β ∈ ℝ^H, running μ̂, σ̂² ∈ ℝ^H, momentum m, ε
Output: y ∈ ℝ^{B × H}, updated μ̂, σ̂² (training only)
Paper formula (Ioffe & Szegedy, ICML 2015, Algorithm 1):

  TRAINING:
    μ_B  = (1/B) · Σ_{b=1..B}  x_{b,j}                    (per-feature)
    σ_B² = (1/B) · Σ_{b=1..B}  (x_{b,j} − μ_B)²
    x̂_{b,j} = (x_{b,j} − μ_B) / sqrt(σ_B² + ε)
    y_{b,j}  = γ_j · x̂_{b,j}  +  β_j

    # Update running stats (paper §3.1):
    μ̂_j   ← (1 − m)·μ̂_j + m·μ_B_j
    σ̂²_j  ← (1 − m)·σ̂²_j + m·σ_B²_j

  INFERENCE:
    y_{b,j} = γ_j · (x_{b,j} − μ̂_j) / sqrt(σ̂²_j + ε)  +  β_j
```

- **Time complexity:** O(B · H)
- **Space complexity:** O(B · H) output + O(H) running stats
- **Convergence:** Reduces internal covariate shift; typically 2–10x faster training convergence

## Academic Source
Ioffe, S. & Szegedy, C. "Batch Normalization: Accelerating Deep Network Training by Reducing Internal Covariate Shift." *Proceedings of the 32nd International Conference on Machine Learning (ICML 2015)*, PMLR 37:448–456. arXiv:1502.03167. URL: https://proceedings.mlr.press/v37/ioffe15.html.

## C++ Interface (pybind11)

```cpp
// BatchNorm forward; training=true updates running stats in place
std::tuple<py::array_t<float>, py::array_t<float>, py::array_t<float>>
batch_norm_forward(
    py::array_t<float, py::array::c_style | py::array::forcecast> x,       // (B, H)
    py::array_t<float, py::array::c_style | py::array::forcecast> gamma,   // (H,)
    py::array_t<float, py::array::c_style | py::array::forcecast> beta,    // (H,)
    py::array_t<float, py::array::c_style> running_mean,   // (H,)  in/out
    py::array_t<float, py::array::c_style> running_var,    // (H,)  in/out
    bool training, float momentum = 0.1f, float eps = 1e-5f
);
```

## Memory Budget
- Runtime RAM: <40 MB at B=1024, H=1024 (y + saved μ, σ for backward)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: output numpy once per call; no heap in inner loop

## Performance Target
- Baseline: `torch.nn.functional.batch_norm` CPU
- Target: ≥4x faster at (B=1024, H=1024)
- Benchmark: 3 sizes — (B=32, H=128), (B=256, H=512), (B=1024, H=1024)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** OpenMP parallel-reduce over batch axis for μ_B and σ_B² (per feature). No shared writes during forward. No `volatile`.

**Memory:** No raw `new`/`delete`. Running stats are caller-owned and updated in place. Bounds-checked shapes in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for strides.

**SIMD:** AVX2 FMA for two-pass Welford reduction. `_mm256_zeroupper()` before return. `alignas(64)` on feature axis.

**Floating point:** Double accumulator for batch sums when B > 512. NaN/Inf check on input. ε guards sqrt.

**Performance:** No `std::endl`. No `std::function`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on B = 0 in training mode (paper undefined).

**Build:** No cyclic includes. Anonymous namespace for reduction helpers.

**Security:** No `system()`. No TOCTOU on running-stats buffers.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_215.py` | Forward output + updated running stats match PyTorch within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than PyTorch CPU at all 3 sizes |
| 5 | `pytest test_edges_meta_215.py` | B=1 training (rejected), B=1 inference OK, constant feature, NaN reject pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
- **Stage owned:** Cross-sample feature normalisation in ranker MLP training
- **Owns:** Training + inference BatchNorm with running-stat update
- **Alternative to:** META-214 (LayerNorm — per-sample), META-216 (GroupNorm — grouped)
- **Coexists with:** META-217/218 (weight-side normalisation); BatchNorm on activations + WeightNorm on weights is a documented pairing

## Test Plan
- B=32 random input: verify training-mode y has feature-wise mean ≈ β and var ≈ γ² within 1e-5
- Inference mode with known running stats: verify formula matches PyTorch bit-for-bit
- B=1 training: verify raises `py::value_error` (variance undefined)
- B=1 inference: verify accepted, uses running stats
- Constant feature column: verify ε prevents div-by-zero
