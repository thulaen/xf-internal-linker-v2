# META-217 — Weight Normalisation (WeightNorm)

## Overview
**Category:** Weight reparameterisation (decouple magnitude and direction)
**Extension file:** `weight_norm.cpp`
**Replaces/improves:** `torch.nn.utils.weight_norm` forward path for every linear layer in the ranker that pairs with BatchNorm / LayerNorm
**Expected speedup:** ≥4x for the fused forward reparam + matmul
**RAM:** <20 MB for layer 4096 × 4096 | **Disk:** <1 MB

## Algorithm

```
Input:  trained direction v ∈ ℝ^{n_out × n_in}, magnitude scalar g ∈ ℝ^{n_out}
Output: effective weight w ∈ ℝ^{n_out × n_in}
Paper formula (Salimans & Kingma, NIPS 2016, Eq. 2):

  For each output row i:
    w_i = g_i · (v_i / ‖v_i‖)

  Equivalently, element-wise:
    w_{i,j} = g_i · v_{i,j} / sqrt( Σ_k v_{i,k}² )

The two learnable pieces:
  - direction:  v  (same shape as w; the unit-norm direction is v_i / ‖v_i‖)
  - magnitude:  g  (one scalar per output; controls row length independently)

Gradient (paper §2.2):
  ∂L/∂g_i = (v_iᵀ · ∂L/∂w_i) / ‖v_i‖
  ∂L/∂v_i = (g_i / ‖v_i‖) · ∂L/∂w_i  −  (g_i · ∂L/∂g_i / ‖v_i‖²) · v_i
```

- **Time complexity:** O(n_out · n_in) forward reparam
- **Space complexity:** O(n_out · n_in) for w; O(n_out) for stored ‖v_i‖
- **No running stats:** purely a weight transform; training and inference identical

## Academic Source
Salimans, T. & Kingma, D. P. "Weight Normalization: A Simple Reparameterization to Accelerate Training of Deep Neural Networks." *Advances in Neural Information Processing Systems 29 (NIPS 2016)*, 901–909. arXiv:1602.07868. URL: https://proceedings.neurips.cc/paper/2016/hash/ed265bc903a5a097f61d3ec064d96d2e-Abstract.html.

## C++ Interface (pybind11)

```cpp
// WeightNorm forward: w = g * v / ||v|| (per row); returns (w, row_norms)
std::tuple<py::array_t<float>, py::array_t<float>>
weight_norm_forward(
    py::array_t<float, py::array::c_style | py::array::forcecast> v,  // (n_out, n_in)
    py::array_t<float, py::array::c_style | py::array::forcecast> g,  // (n_out,)
    float eps = 1e-12f
);
```

## Memory Budget
- Runtime RAM: <20 MB at 4096 × 4096 (w output + row_norms cache)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: output numpy once per call; no heap in inner loop

## Performance Target
- Baseline: `torch.nn.utils.weight_norm` CPU path (reparam + matmul)
- Target: ≥4x faster fused reparam alone
- Benchmark: 3 sizes — (64 × 64), (512 × 512), (4096 × 4096)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** OpenMP across output rows (i axis); each row independent (its own norm). No `volatile`. Writes are disjoint.

**Memory:** No raw `new`/`delete`. Output buffer from numpy. Bounds-checked shapes in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for strides.

**SIMD:** AVX2 FMA for row dot product v_iᵀ v_i, then vectorised scale. `_mm256_zeroupper()` before return. `alignas(64)` on row blocks.

**Floating point:** Double accumulator for row norms when n_in > 1024. ε = 1e-12 guards divide by zero. NaN/Inf reject on v or g.

**Performance:** No `std::endl`. No `std::function`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on zero-norm row (if eps disabled) or shape mismatch.

**Build:** No cyclic includes. Anonymous namespace for norm helper.

**Security:** No `system()`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_217.py` | Output matches PyTorch weight_norm within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than PyTorch CPU at all 3 sizes |
| 5 | `pytest test_edges_meta_217.py` | Zero-norm row, n_in=1, n_out=1, NaN reject pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
- **Stage owned:** Weight-side reparameterisation on linear layers in the ranker / reranker
- **Owns:** `w = g · v / ‖v‖` forward (and saved row_norms for backward)
- **Alternative to:** META-218 (SpectralNorm — different weight-side normalisation; Lipschitz control)
- **Coexists with:** META-214/215/216 (activation normalisation is orthogonal); META-211/212/213 (initialisation runs upstream of reparam)

## Test Plan
- Random v, g=1: verify each output row of w has unit norm within 1e-6
- Random v, g=scale: verify row norm of w = |g_i|
- Zero-norm row v_i = 0 with eps: verify w_i = 0, no NaN
- Zero-norm row v_i = 0 with eps disabled: verify raises `py::value_error`
- Reproducibility: same v, g → bit-identical w on same hardware
