# META-157 — Random Projection (Johnson-Lindenstrauss)

## Overview
**Category:** Dimensionality reduction (linear, data-oblivious)
**Extension file:** `random_projection_jl.cpp`
**Replaces/improves:** `sklearn.random_projection.SparseRandomProjection` for fast pre-filtering of high-dim vectors before nearest-neighbour
**Expected speedup:** ≥10x over scikit-learn for `d ≥ 4096` (no data scan required)
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

```
Input: target pairwise distortion ε ∈ (0, 1), n points in ℝ^d, seed
Output: projection Φ ∈ ℝ^{m×d} with m = ⌈8·log n / ε²⌉

Achlioptas sparse construction:
    Φ_ij = (1/√m) · {
        +1  w.p. 1/6
         0  w.p. 2/3
        −1  w.p. 1/6
    }

Transform any x ∈ ℝ^d:
    x' = Φ · x              // m-dimensional

Guarantee (JL lemma):
    ∀ i,j:  (1 − ε)·‖x_i − x_j‖² ≤ ‖Φ·x_i − Φ·x_j‖² ≤ (1 + ε)·‖x_i − x_j‖²   w.p. ≥ 1 − 2/n
```

- **Time complexity:** O(m·d) to build Φ, O(n·m·d) to transform n points — with sparse matrix this drops to O(n·m·d/3)
- **Space complexity:** O(m·d) for Φ (two-thirds zeros — store as CSR)
- **Convergence:** Probabilistic guarantee per JL lemma; no iteration

## Academic Source
Johnson, W. B., & Lindenstrauss, J. (1984). "Extensions of Lipschitz mappings into a Hilbert space." *Contemporary Mathematics*, 26, 189–206.
Achlioptas, D. (2003). "Database-friendly random projections: Johnson-Lindenstrauss with binary coins." *Journal of Computer and System Sciences*, 66(4), 671–687.

## C++ Interface (pybind11)

```cpp
struct JLProjector {
    std::vector<float> values;   // non-zeros of Φ (CSR)
    std::vector<int> indices;    // column indices
    std::vector<int> indptr;     // row pointers, length m+1
    int m, d;
};
JLProjector jl_build(int n, int d, float epsilon, uint32_t seed,
                     const char* density);    // "sqrt_d" | "one_third"

std::vector<float> jl_transform(
    const JLProjector& P,
    const float* X, int n_x, int d
);
```

## Memory Budget
- Runtime RAM: <20 MB for m=2048, d=8192 (sparse ≈ 22 MB dense equivalent → 7 MB CSR)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(nnz + m + 1)`, `alignas(64)` on dense output

## Performance Target
- Python baseline: `sklearn.random_projection.SparseRandomProjection(eps=ε).fit_transform(X)`
- Target: ≥10x faster via CSR SpMV with SIMD accumulators
- Benchmark sizes: (n=10k, d=1024, ε=0.3), (n=100k, d=4096, ε=0.2), (n=1M, d=8192, ε=0.1)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` — see `backend/extensions/CPP-RULES.md`.

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. RNG is thread-local; projection build uses per-row seeds for reproducibility.

**Memory:** No raw `new`/`delete`. No `alloca`/VLA. RAII only. CSR buffers owned by `std::vector`.

**Object lifetime:** Self-assignment safe. No dangling views. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` narrowing with comment. `epsilon ∈ (0,1)` validated. `n, d > 0` validated.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. `alignas(64)` on dense output buffer. SpMV uses gather/scatter-free inner loop.

**Floating point:** FTZ on init. NaN/Inf entry check. Double accumulator for row dot-products if d > 8192.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Anonymous namespace for RNG helpers.

**Security:** No `system()`. No `printf(user_string)`. RNG seed parameter documented. Seed=0 rejected (ambiguous).

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_157.py` | Pairwise distance distortion within [1−ε, 1+ε] for 99.9% of pairs |
| 3 | `ASAN=1 build + pytest` | Zero errors |
| 4 | `bench_extensions.py` | ≥10x faster at all 3 sizes |
| 5 | `pytest test_edges_meta_157.py` | n=1, d=1, ε near 1, constant input all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone; pure CSR SpMV)

## Pipeline Stage & Non-Conflict
- **Stage:** Pre-filter / approximate nearest-neighbour pre-processing
- **Owns:** Data-oblivious dimensionality reduction with distortion guarantee
- **Alternative to:** META-151 (PCA — needs data scan), META-152 (kernel PCA)
- **Coexists with:** META-161 (RFF — different randomised structure for kernel approx)

## Test Plan
- JL distortion: sample 1000 pairs from Gaussian input, verify ‖·‖² distortion ≤ ε for 99.9%
- Seed reproducibility: same seed → byte-identical Φ
- Achlioptas density: ≈2/3 of entries are zero within 1% tolerance
- Benchmark vs. sklearn on 100k×4096 input: memory ≤ 1.5× sklearn, speed ≥ 10×
- Constant input: output norms preserved (zero distortion on all-equal pairs)
