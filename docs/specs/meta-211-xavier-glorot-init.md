# META-211 — Xavier / Glorot Initialisation

## Overview
**Category:** Neural-network weight initialisation
**Extension file:** `init_xavier.cpp`
**Replaces/improves:** Python `torch.nn.init.xavier_uniform_` wrapper in learned-to-rank MLP builder
**Expected speedup:** ≥3x for bulk initialisation of all layers at model build time
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input:  layer shape (n_in, n_out), fill mode ∈ {uniform, normal}, gain
Output: weight matrix W ∈ ℝ^{n_in × n_out}
Paper formula (Glorot & Bengio, AISTATS 2010, Eq. 16):

  Uniform variant:
    W_ij ~ U[ −a, +a ]    with  a = gain · sqrt( 6 / (n_in + n_out) )

  Normal variant (common restatement):
    W_ij ~ N( 0, σ² )     with  σ² = gain² · 2 / (n_in + n_out)

Goal: preserve activation variance and gradient variance jointly through a linear layer
      by balancing fan_in and fan_out.
```

- **Time complexity:** O(n_in · n_out) per layer (single pass of RNG + scale)
- **Space complexity:** O(n_in · n_out)
- **Note:** gain = 1.0 for identity / linear; 5/3 for tanh; √2 for ReLU (though META-212 is preferred for ReLU)

## Academic Source
Glorot, X. & Bengio, Y. "Understanding the difficulty of training deep feedforward neural networks." *Proceedings of the 13th International Conference on Artificial Intelligence and Statistics (AISTATS 2010)*, PMLR 9:249–256. URL: https://proceedings.mlr.press/v9/glorot10a.html. (No DOI; canonical paper.)

## C++ Interface (pybind11)

```cpp
// Xavier/Glorot weight init (in-place on a pre-allocated numpy float array)
void xavier_init(
    py::array_t<float, py::array::c_style | py::array::forcecast> W,
    int n_in, int n_out,
    float gain = 1.0f,
    bool use_uniform = true,
    uint64_t seed = 0
);
```

## Memory Budget
- Runtime RAM: <10 MB (RNG state only; W is caller-owned)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: zero heap allocation in fill loop; per-thread `std::mt19937_64` state reused

## Performance Target
- Baseline: numpy `np.random.uniform(-a, +a, (n_in, n_out))`
- Target: ≥3x faster by fusing RNG + scale + write in one AVX2 pass
- Benchmark: 3 sizes — (64 × 64), (512 × 512), (4096 × 4096)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** Optional OpenMP across output columns; per-thread splittable RNG. No `volatile`. Document memory ordering (none required — writes are disjoint).

**Memory:** No raw `new`/`delete`. W is caller-owned numpy buffer. Bounds-checked shape in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast<size_t>` for shape arithmetic. No signed/unsigned mismatch.

**SIMD:** AVX2 vectorised uniform sampling via batched 8×32-bit xoshiro output to float. `_mm256_zeroupper()` before return. `alignas(64)` not required (caller buffer).

**Floating point:** `a = gain · sqrtf(6.f / (n_in + n_out))` computed once. Reject n_in+n_out = 0 with `py::value_error`. No NaN possible in fill path.

**Performance:** No `std::endl`. No `std::function`. `return;` (void).

**Error handling:** Destructors `noexcept`. Raise on negative dimensions or W shape mismatch.

**Build:** No cyclic includes. Anonymous namespace for RNG helpers.

**Security:** No `system()`. Seed comes from caller; no implicit `/dev/urandom` read.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_211.py` | Variance of fill within 2% of theoretical 2/(n_in+n_out) |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than numpy at all 3 sizes |
| 5 | `pytest test_edges_meta_211.py` | n_in=1, n_out=1, uniform+normal modes, zero-dim rejection pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone)

## Pipeline Stage Non-Conflict
- **Stage owned:** Layer-weight initialisation at model construction
- **Owns:** Glorot uniform/normal fill
- **Alternative to:** META-212 (He init — for ReLU), META-213 (orthogonal init — for RNN / deep nets)
- **Coexists with:** META-214/215/216/217/218 (normalisation layers sit after init; all can compose)

## Test Plan
- Fill 10000×10000: verify empirical variance = 2/(n_in+n_out) ± 2%
- Uniform mode: verify min and max ≈ ±a within sample bounds
- Normal mode: verify KS-test against N(0, σ²) at p > 0.01
- Zero dimension: verify raises `py::value_error`
- Reproducibility: same seed → bit-identical output on same hardware
