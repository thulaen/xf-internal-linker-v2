# META-216 — Group Normalisation (GroupNorm)

## Overview
**Category:** Activation normalisation (grouped, batch-size-independent)
**Extension file:** `group_norm.cpp`
**Replaces/improves:** `torch.nn.functional.group_norm` CPU path for any small-batch reranker training where BatchNorm is unstable
**Expected speedup:** ≥4x over PyTorch CPU at typical channel counts
**RAM:** <30 MB for batch=32, C=512, spatial=16 | **Disk:** <1 MB

## Algorithm

```
Input:  x ∈ ℝ^{B × C × *}, γ, β ∈ ℝ^C, number of groups G (C divisible by G), ε
Output: y ∈ ℝ^{B × C × *}
Paper formula (Wu & He, ECCV 2018, Eq. 3):

  Split C into G groups of size C/G.
  For each (b, g) pair, compute stats over {group-g channels} × {spatial positions}:

    μ_G = (1 / (C/G · |spatial|)) · Σ_{c ∈ group_g, s ∈ spatial}  x_{b,c,s}
    σ_G² = (1 / (C/G · |spatial|)) · Σ_{c ∈ group_g, s ∈ spatial}  (x_{b,c,s} − μ_G)²

  Normalise and affine-transform:
    y_{b,c,s} = ((x_{b,c,s} − μ_G) / sqrt(σ_G² + ε)) · γ_c  +  β_c

Key property: independent of batch size B (LayerNorm is G=1; InstanceNorm is G=C).
```

- **Time complexity:** O(B · C · |spatial|)
- **Space complexity:** O(B · C · |spatial|) output + O(B · G) saved stats for backward
- **No running stats:** identical forward in training and inference

## Academic Source
Wu, Y. & He, K. "Group Normalization." *Proceedings of the European Conference on Computer Vision (ECCV 2018)*, 3–19. Also *International Journal of Computer Vision* 128 (2020). DOI: 10.1007/s11263-019-01198-w (journal); ECCV proceedings: 10.1007/978-3-030-01261-8_1.

## C++ Interface (pybind11)

```cpp
// GroupNorm forward; C must be divisible by G; returns (y, saved_mean, saved_invstd)
std::tuple<py::array_t<float>, py::array_t<float>, py::array_t<float>>
group_norm_forward(
    py::array_t<float, py::array::c_style | py::array::forcecast> x,     // (B, C, *)
    py::array_t<float, py::array::c_style | py::array::forcecast> gamma, // (C,)
    py::array_t<float, py::array::c_style | py::array::forcecast> beta,  // (C,)
    int num_groups,
    float eps = 1e-5f
);
```

## Memory Budget
- Runtime RAM: <30 MB at B=32, C=512, spatial=16 (y + saved μ, invstd)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: output numpy once per call; no heap in inner loop

## Performance Target
- Baseline: `torch.nn.functional.group_norm` CPU
- Target: ≥4x faster at (B=32, C=512, spatial=16)
- Benchmark: 3 sizes — (B=4, C=64, s=8, G=8), (B=16, C=256, s=16, G=16), (B=32, C=512, s=16, G=32)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** OpenMP across (b, g) pairs — fully independent normalisation. No shared writes. No `volatile`.

**Memory:** No raw `new`/`delete`. Output buffer from numpy. Bounds-checked shapes + C % G == 0 in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for stride arithmetic.

**SIMD:** AVX2 FMA for two-pass Welford reduction over (channels_in_group × spatial). `_mm256_zeroupper()` before return. `alignas(64)` on channel blocks.

**Floating point:** Double accumulator when group-size × spatial > 1024. NaN/Inf check on input. ε guards sqrt.

**Performance:** No `std::endl`. No `std::function`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on C not divisible by G.

**Build:** No cyclic includes. Anonymous namespace for reduction helpers.

**Security:** No `system()`. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_216.py` | Output matches PyTorch group_norm within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥4x faster than PyTorch CPU at all 3 sizes |
| 5 | `pytest test_edges_meta_216.py` | G=1 (== LayerNorm), G=C (== InstanceNorm), non-divisible reject, NaN reject pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
- **Stage owned:** Grouped-channel feature normalisation in reranker CNN-style heads
- **Owns:** Forward + backward GroupNorm with configurable G
- **Alternative to:** META-214 (LayerNorm — G=1), META-215 (BatchNorm — batch-coupled)
- **Coexists with:** META-217/218 (weight-side normalisation layers are orthogonal)

## Test Plan
- G=1: verify numerical equivalence to LayerNorm (META-214) within 1e-6
- G=C: verify numerical equivalence to InstanceNorm formula
- C not divisible by G: verify raises `py::value_error`
- Constant-input group: verify ε prevents div-by-zero
- NaN input: verify raises `py::value_error`
