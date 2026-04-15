# META-212 — He (Kaiming) Initialisation

## Overview
**Category:** Neural-network weight initialisation (ReLU-family)
**Extension file:** `init_he.cpp`
**Replaces/improves:** Python `torch.nn.init.kaiming_normal_` wrapper; default for any ReLU-activated layer in the ranker MLP
**Expected speedup:** ≥3x for bulk init at model build time
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input:  layer shape (n_in, n_out), mode ∈ {fan_in, fan_out}, nonlinearity
Output: W ∈ ℝ^{n_in × n_out}
Paper formula (He, Zhang, Ren, Sun, ICCV 2015, Eq. 10):

  For ReLU:
    W_ij ~ N( 0, σ² )   with   σ² = 2 / n_l
    where n_l = fan_in (default) or fan_out (variant)

  For Leaky ReLU with negative slope α:
    σ² = 2 / ((1 + α²) · n_l)

Reasoning: preserves the forward-pass activation variance through a ReLU layer,
which kills half the signal on average. Xavier under-scales by a factor of √2.
```

- **Time complexity:** O(n_in · n_out) per layer
- **Space complexity:** O(n_in · n_out)
- **Note:** Use He over Xavier whenever the following nonlinearity is ReLU / LeakyReLU / PReLU.

## Academic Source
He, K., Zhang, X., Ren, S. & Sun, J. "Delving Deep into Rectifiers: Surpassing Human-Level Performance on ImageNet Classification." *Proceedings of the IEEE International Conference on Computer Vision (ICCV 2015)*, 1026–1034. DOI: 10.1109/ICCV.2015.123.

## C++ Interface (pybind11)

```cpp
// He/Kaiming weight init (in-place on a pre-allocated numpy float array)
void he_init(
    py::array_t<float, py::array::c_style | py::array::forcecast> W,
    int n_in, int n_out,
    bool use_fan_in = true,
    float negative_slope = 0.0f,   // 0 = ReLU; >0 = LeakyReLU α
    bool use_normal = true,        // false = uniform variant
    uint64_t seed = 0
);
```

## Memory Budget
- Runtime RAM: <10 MB (RNG state only)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: zero heap allocation in fill loop

## Performance Target
- Baseline: `torch.nn.init.kaiming_normal_` via CPU path
- Target: ≥3x faster by fusing RNG + scale in AVX2 pass
- Benchmark: 3 sizes — (64 × 64), (512 × 512), (4096 × 4096)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** Optional OpenMP across output columns; per-thread splittable RNG. No `volatile`. Writes are disjoint.

**Memory:** No raw `new`/`delete`. W is caller-owned. Bounds-checked shape in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch.

**SIMD:** AVX2 Gaussian generation via Box-Muller or Ziggurat on batched xoshiro output. `_mm256_zeroupper()` before return.

**Floating point:** `σ = sqrtf(2.f / ((1.f + α²) · n_l))` computed once. Reject n_l = 0. No NaN in fill path.

**Performance:** No `std::endl`. No `std::function`. `return;` (void).

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on negative dims or shape mismatch.

**Build:** No cyclic includes. Anonymous namespace for RNG helpers.

**Security:** No `system()`. No implicit `/dev/urandom`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_212.py` | Variance of fill within 2% of theoretical 2/n_l |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than PyTorch CPU at all 3 sizes |
| 5 | `pytest test_edges_meta_212.py` | n_in=1, LeakyReLU α=0.1, fan_out mode, zero-dim reject pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
- **Stage owned:** Layer-weight initialisation for ReLU-family layers
- **Owns:** Kaiming normal/uniform fill with mode and slope parameters
- **Alternative to:** META-211 (Xavier — tanh/linear), META-213 (orthogonal — deep/RNN)
- **Coexists with:** META-214/215/216/217/218 (normalisation applied after init is orthogonal)

## Test Plan
- Fill 10000×10000: verify empirical variance = 2/n_l ± 2%
- LeakyReLU α=0.1: verify variance = 2/((1+0.01)·n_l) ± 2%
- fan_in vs fan_out mode: verify variance tracks the selected n_l
- Zero dimension: verify raises `py::value_error`
- Reproducibility: same seed → bit-identical output on same hardware
