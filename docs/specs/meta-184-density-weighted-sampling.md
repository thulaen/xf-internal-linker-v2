# META-184 — Density-Weighted Sampling

## Overview
**Category:** Active learning query strategy (outlier-robust)
**Extension file:** `density_weighted_sampling.cpp`
**Replaces/improves:** Pure uncertainty (META-181) that over-samples outliers in the unlabelled pool
**Expected speedup:** ≥7x over Python sklearn cosine_similarity mean loop
**RAM:** <64 MB | **Disk:** <1 MB

## Algorithm

```
Input: unlabeled pool U = {x_1..x_N}, uncertainty score u(x), similarity sim(x,x'), β > 0
Output: next query x* balancing uncertainty and representativeness

for each x in U:
    density(x) = (1/|U|) · Σ_{x' in U} sim(x, x')       // average similarity to pool
    score(x) = uncertainty(x) · density(x)^β

x* = argmax_{x in U} uncertainty(x) · ((1/|U|) · Σ_{x' in U} sim(x, x'))^β
```

- **Paper update rule (Settles):** `x* = argmax_x uncertainty(x) · ( (1/|U|)·Σ_{x'∈U} sim(x,x') )^β`
- **Time complexity:** O(|U|²) pairwise sim or O(|U| · k) with k-NN approximation
- **Space complexity:** O(|U|) density vector

## Academic Source
Settles, B. (2012). "Active Learning". Synthesis Lectures on Artificial Intelligence and Machine Learning, Morgan & Claypool, Vol. 6, No. 1, pp. 1-114. DOI: 10.2200/S00429ED1V01Y201207AIM018

## C++ Interface (pybind11)

```cpp
// Uncertainty + dense similarity matrix (|U|x|U|) OR sparse k-NN neighbours
std::vector<int> density_weighted_sampling(
    const float* uncertainty,  // [n_samples]
    const float* sim_matrix,   // [n_samples, n_samples] symmetric
    int n_samples, float beta,
    int top_k
);
```

## Memory Budget
- Runtime RAM: <64 MB — dense sim_matrix at |U|=4000 uses 64 MB; larger |U| requires k-NN sparse variant
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: one `std::vector<float>` density row-reduction, reused

## Performance Target
- Python baseline: `sklearn.metrics.pairwise.cosine_similarity(U).mean(axis=1)`
- Target: ≥7x faster (blocked GEMM-style row reduction, SIMD FMA)
- Benchmark: 3 sizes — |U|=500, 2000, 4000

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Row-parallel reduction via OpenMP. Private row accumulator.

**Memory:** No raw `new`/`delete`. `reserve()` before fills. Bounds-checked in debug.

**Object lifetime:** Read-only sim_matrix pointer; no dangling refs.

**Type safety:** Explicit `static_cast` narrowing. No signed/unsigned mismatch.

**SIMD:** AVX2 FMA horizontal sum; `_mm256_zeroupper()` on exit. `alignas(64)` on sim rows.

**Floating point:** Double accumulator for |U| ≥ 1000. `std::pow(density, beta)` or `exp(beta·log(density))` for β ≠ 1.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Blocked tile for cache.

**Error handling:** Validate `beta ≥ 0`. Clamp density to [1e-12, 1]. Destructors `noexcept`. pybind11 catches.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_184.py` | Matches numpy reference within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥7x faster than sklearn reference |
| 5 | `pytest test_edges_meta_184.py` | β=0 (no density), β=1, singleton |U|=1, all-identical |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP parallel loop |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Consumes uncertainty from META-181 or disagreement from META-182

## Pipeline Stage Non-Conflict
- **Owns:** Representativeness-weighted query scoring
- **Alternative to:** META-181 (pure uncertainty), META-182 (QBC), META-183 (EMC)
- **Coexists with:** META-185 (batch-mode AL) — batch builder consumes these per-sample scores

## Test Plan
- β=0: verify score reduces to uncertainty (identity)
- Uniform sim=1 matrix: verify density = 1 for all samples
- Singleton |U|=1: verify density = sim(x,x) and score well-defined
- Negative β: verify raises ValueError
- NaN in sim_matrix: verify raises ValueError
