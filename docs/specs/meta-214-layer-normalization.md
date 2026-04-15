# META-214 — Layer Normalisation (LayerNorm)

## Overview
**Category:** Activation normalisation (per-sample)
**Extension file:** `layer_norm.cpp`
**Replaces/improves:** `torch.nn.functional.layer_norm` CPU path for per-sample feature normalisation in the learned-to-rank MLP and cross-encoder reranker
**Expected speedup:** ≥4x over PyTorch CPU at typical hidden dims
**RAM:** <20 MB for batch=1024, H=1024 | **Disk:** <1 MB

## Algorithm

```
Input:  x ∈ ℝ^{B × H}, learnable γ, β ∈ ℝ^H, ε
Output: y ∈ ℝ^{B × H}
Paper formula (Ba, Kiros, Hinton, arXiv:1607.06450, Eq. 3):

  For each sample b ∈ 1..B (independently; NO batch coupling):
    μ_L = (1/H) · Σ_{j=1..H}  x_{b,j}
    σ_L² = (1/H) · Σ_{j=1..H}  (x_{b,j} − μ_L)²
    y_{b,j} = ((x_{b,j} − μ_L) / sqrt(σ_L² + ε)) · γ_j  +  β_j

Key property (vs BatchNorm): statistics come from the feature axis of ONE sample,
so inference == training; no running averages needed; safe for RNN / variable-batch.
```

- **Time complexity:** O(B · H) forward; same for backward
- **Space complexity:** O(B · H) output + O(B) saved (μ, σ) for backward
- **No state:** pure function once γ, β are fixed

## Academic Source
Ba, J. L., Kiros, J. R. & Hinton, G. E. "Layer Normalization." arXiv:1607.06450 (2016). URL: https://arxiv.org/abs/1607.06450. (Widely cited; no journal DOI, arXiv identifier is canonical.)

## C++ Interface (pybind11)

```cpp
// LayerNorm forward; returns (y, saved_mean, saved_invstd) for backward
std::tuple<py::array_t<float>, py::array_t<float>, py::array_t<float>>
layer_norm_forward(
    py::array_t<float, py::array::c_style | py::array::forcecast> x,  // (B, H)
    py::array_t<float, py::array::c_style | py::array::forcecast> gamma, // (H,)
    py::array_t<float, py::array::c_style | py::array::forcecast> beta,  // (H,)
    float eps = 1e-5f
);
```

## Memory Budget
- Runtime RAM: <20 MB at B=1024, H=1024 (y + mean + invstd)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: output numpy arrays allocated once per call; no heap in inner loop

## Performance Target
- Baseline: `torch.nn.functional.layer_norm` CPU
- Target: ≥4x faster at (B=1024, H=1024)
- Benchmark: 3 sizes — (B=32, H=128), (B=256, H=512), (B=1024, H=1024)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** OpenMP `parallel for` across samples (b axis); each sample independent. No shared state. No `volatile`.

**Memory:** No raw `new`/`delete`. Output buffers allocated via numpy (pybind11). Bounds-checked shapes in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for stride arithmetic.

**SIMD:** AVX2 FMA for the two-pass sum (Welford recommended to avoid catastrophic cancellation at H > 4096). `_mm256_zeroupper()` before return. `alignas(64)` per-sample rows.

**Floating point:** Double accumulator for μ and σ² when H > 1024. NaN/Inf check on input. ε guards divide by sqrt.

**Performance:** No `std::endl`. No `std::function`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on shape mismatch or H = 0.

**Build:** No cyclic includes. Anonymous namespace for per-sample kernel.

**Security:** No `system()`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_214.py` | Output matches PyTorch layer_norm within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than PyTorch CPU at all 3 sizes |
| 5 | `pytest test_edges_meta_214.py` | H=1, B=1, all-zero input, NaN reject pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
- **Stage owned:** Per-sample feature normalisation inside the ranker MLP
- **Owns:** Forward + backward LayerNorm over the last axis
- **Alternative to:** META-215 (BatchNorm — cross-sample stats), META-216 (GroupNorm — grouped stats), META-217 (WeightNorm — weight-side reparam), META-218 (SpectralNorm — Lipschitz control)
- **Coexists with:** META-211/212/213 (initialisation is upstream of normalisation)

## Test Plan
- Constant input row: verify y = β exactly (numerator = 0)
- Random input B=1024, H=1024: verify mean(y)_row ≈ β, var(y)_row ≈ γ² within 1e-5
- H=1: verify σ² = 0, ε prevents div-by-zero, output = β
- NaN input: verify raises `py::value_error`
- Numerical stability at H=8192: verify no Inf using Welford path
