# META-207 — Non-negative Matrix Factorisation (NMF)

## Overview
**Category:** Matrix factorisation (non-negative, parts-based)
**Extension file:** `nmf.cpp`
**Replaces/improves:** `sklearn.decomposition.NMF` multiplicative-update solver for topic / cluster loadings over link-feature matrices
**Expected speedup:** ≥6x over sklearn (pure numpy backend) for medium matrices
**RAM:** <80 MB for 10k×500 rank-32 | **Disk:** <1 MB

## Algorithm

```
Input:  V ∈ ℝ_+^{m×n} (V ≥ 0), rank k
Output: W ∈ ℝ_+^{m×k}, H ∈ ℝ_+^{k×n}
Paper objective: min_{W,H ≥ 0}  ‖V − W·H‖_F²

Initialise W, H ~ Uniform(0, sqrt(mean(V)/k))  (or SVD-based NNDSVD)

for iter = 1..max_iter:
    # Paper update rule (Lee & Seung, Nature 1999, Eq. 4):
    H ← H ⊙ (Wᵀ V) / (Wᵀ W H + ε)     # ⊙ element-wise; ε = 1e-10
    W ← W ⊙ (V Hᵀ) / (W H Hᵀ + ε)
    if ‖V − W·H‖_F² − prev < tol:  break
```

- **Time complexity:** O(iters · k · (m + n) · nnz(V))  for sparse V; O(iters · k · m · n) dense
- **Space complexity:** O(m·k + k·n + m·n workspace)
- **Convergence:** Monotone non-increasing of Frobenius objective (proved via auxiliary function in paper)

## Academic Source
Lee, D. D. & Seung, H. S. "Learning the parts of objects by non-negative matrix factorization." *Nature* 401, 788–791 (1999). DOI: 10.1038/44565.

## C++ Interface (pybind11)

```cpp
// Multiplicative-update NMF; returns (W, H) both non-negative
std::tuple<py::array_t<float>, py::array_t<float>>
nmf_mu(
    py::array_t<float, py::array::c_style | py::array::forcecast> V,
    int k,
    int max_iter = 200,
    float tol = 1e-4f,
    uint64_t seed = 0
);
```

## Memory Budget
- Runtime RAM: <80 MB at m=10000, n=500, k=32 (V + W + H + 2 temp workspace)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: reserved once, reused across iterations; no per-iter allocation

## Performance Target
- Baseline: `sklearn.decomposition.NMF(solver='mu')`
- Target: ≥6x faster at (10000×500, k=32)
- Benchmark: 3 sizes — (500×100, k=8), (2000×200, k=16), (10000×500, k=32)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** OpenMP `parallel for` across rows of W and columns of H; document memory ordering. No nested parallelism. No `volatile`.

**Memory:** No raw `new`/`delete`. Arena buffers for WᵀV, WᵀW, HHᵀ temporaries reused each iteration. Bounds-checked in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast`. No signed/unsigned mismatch. `size_t` for index arithmetic in products m·n.

**SIMD:** AVX2 FMA on multiplicative updates; `_mm256_zeroupper()` before return. `alignas(64)` on W, H rows.

**Floating point:** ε = 1e-10 guards denominators. NaN/Inf check on V entry. Reject any V_ij < 0 with `py::value_error`.

**Performance:** Avoid `std::function` in hot loop. `return x;` not `return std::move(x);`. No `std::endl`.

**Error handling:** Destructors `noexcept`. Raise on negative V or k > min(m,n).

**Build:** No cyclic includes. Static internals in anonymous namespace.

**Security:** No `system()`. Scrub sensitive memory on error.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_207.py` | Reconstruction ‖V − WH‖_F matches sklearn within 1% |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than sklearn at all 3 sizes |
| 5 | `pytest test_edges_meta_207.py` | All-zero row, rank=1, negative entry rejection pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone; optional warm-start from META-206 via NNDSVD)

## Pipeline Stage Non-Conflict
- **Stage owned:** Offline non-negative factorisation of co-occurrence / link-feature matrices
- **Owns:** Non-negative W, H with multiplicative updates
- **Alternative to:** META-206 (SVD — signed factors), META-210 (WALS — implicit feedback)
- **Coexists with:** META-208/209 (PMF as probabilistic alternative; the UI may expose both)

## Test Plan
- Synthetic low-rank V = W₀ H₀ with W₀, H₀ ≥ 0: verify recovered W·H reconstructs within 1e-3
- Negative entry in V: verify raises `py::value_error`
- Rank = 1: verify W, H collapse to non-negative vectors of matching norm
- Convergence monotonicity: verify objective non-increasing each iteration
- Seeded reproducibility: same seed → bit-identical output on same hardware
