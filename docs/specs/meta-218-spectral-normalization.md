# META-218 — Spectral Normalisation (SpectralNorm)

## Overview
**Category:** Weight reparameterisation (Lipschitz constraint via top singular value)
**Extension file:** `spectral_norm.cpp`
**Replaces/improves:** `torch.nn.utils.spectral_norm` CPU path for any adversarial / contrastive training component where weight Lipschitz must be bounded by 1
**Expected speedup:** ≥5x via in-house power-iteration avoiding Python-level bookkeeping
**RAM:** <20 MB for layer 4096 × 4096 | **Disk:** <1 MB

## Algorithm

```
Input:  weight W ∈ ℝ^{n_out × n_in}, power-iter buffer u ∈ ℝ^{n_out}, iterations T
Output: normalised Ŵ ∈ ℝ^{n_out × n_in}, σ̂(W), updated u
Paper formula (Miyato, Kataoka, Koyama, Yoshida, ICLR 2018, Eq. 8 + §A):

  Power iteration to estimate σ(W) = largest singular value of W:
    for t = 1..T:
        v ← Wᵀ u / ‖Wᵀ u‖          # v ∈ ℝ^{n_in}
        u ← W  v  / ‖W  v‖          # u ∈ ℝ^{n_out}
    σ̂(W) = uᵀ · W · v               # approximates the top singular value

  Normalise:
    Ŵ = W / σ̂(W)

Running u is persisted across training steps (not recomputed from scratch each call).
After convergence, σ̂ → σ (the exact spectral norm) and Ŵ has spectral norm = 1.
```

- **Time complexity:** O(T · n_out · n_in) per call; T = 1 is standard when u is warm across steps
- **Space complexity:** O(n_out + n_in) for u, v
- **Convergence:** Geometric rate (ratio σ₂/σ₁); T=1 with warm u sufficient in practice

## Academic Source
Miyato, T., Kataoka, T., Koyama, M. & Yoshida, Y. "Spectral Normalization for Generative Adversarial Networks." *International Conference on Learning Representations (ICLR 2018)*. arXiv:1802.05957. URL: https://openreview.net/forum?id=B1QRgziT-.

## C++ Interface (pybind11)

```cpp
// Spectral norm via power iteration; u is updated in place for warm-start across calls
std::tuple<py::array_t<float>, float>     // (W_hat, sigma_hat)
spectral_norm_forward(
    py::array_t<float, py::array::c_style | py::array::forcecast> W,  // (n_out, n_in)
    py::array_t<float, py::array::c_style> u,                         // (n_out,) in/out
    int n_power_iter = 1,
    float eps = 1e-12f
);
```

## Memory Budget
- Runtime RAM: <20 MB at 4096 × 4096 (Ŵ output + v workspace)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: scratch `std::vector<float>` for v reserved once, reused across iterations

## Performance Target
- Baseline: `torch.nn.utils.spectral_norm` CPU
- Target: ≥5x faster at (4096 × 4096), T=1, warm u
- Benchmark: 3 sizes — (64 × 64, T=3), (512 × 512, T=1), (4096 × 4096, T=1)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** OpenMP parallel-reduce for W·v and Wᵀ·u matvecs. u, v are per-call (not shared across threads). No `volatile`.

**Memory:** No raw `new`/`delete`. v workspace reserved once. u is caller-owned (warm-state). Bounds-checked shapes in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for strides.

**SIMD:** AVX2 FMA for matvec W·v and Wᵀ·u. `_mm256_zeroupper()` before return. `alignas(64)` on row blocks.

**Floating point:** Double accumulator for norms when dim > 1024. ε = 1e-12 guards L2-normalise of u, v. NaN/Inf check on W.

**Performance:** No `std::endl`. No `std::function`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on σ̂ ≤ eps (degenerate W).

**Build:** No cyclic includes. Anonymous namespace for matvec helpers.

**Security:** No `system()`. No TOCTOU on u buffer.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_218.py` | σ̂ within 1% of numpy svd top singular value after T=5 cold iters |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than PyTorch CPU at all 3 sizes |
| 5 | `pytest test_edges_meta_218.py` | Rank-1 W, zero W reject, n_in=1, warm-u convergence pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- May share matvec kernels with META-206 (SVD) if implemented concurrently; factor into common header.

## Pipeline Stage Non-Conflict
- **Stage owned:** Weight-side Lipschitz control on any linear layer that needs spectral norm ≤ 1 (adversarial / contrastive reranker variants)
- **Owns:** Forward reparam `Ŵ = W / σ̂(W)` with warm-start u
- **Alternative to:** META-217 (WeightNorm — decouples magnitude, no Lipschitz bound)
- **Coexists with:** META-214/215/216 (activation normalisation is orthogonal); META-211/212/213 (initialisation runs upstream)

## Test Plan
- Known-SVD matrix with σ₁ = 5: verify σ̂ → 5 within 1% after T=10 cold iters, and Ŵ has spectral norm 1
- Warm u across 100 calls with slowly changing W: verify σ̂ tracks within 1% at T=1
- Rank-1 W: verify σ̂ = ‖W‖_F (single non-zero σ), Ŵ has unit spectral norm
- Zero W: verify raises `py::value_error`
- Reproducibility: same W and u → bit-identical σ̂ and Ŵ
