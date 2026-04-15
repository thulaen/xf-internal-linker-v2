# META-188 — Label Propagation (Graph)

## Overview
**Category:** Semi-supervised learning (graph-based global consistency)
**Extension file:** `label_propagation.cpp`
**Replaces/improves:** Local pseudo-labelling (META-186/187) when a similarity graph over samples is available
**Expected speedup:** ≥6x over Python scipy sparse matrix power iteration
**RAM:** <80 MB | **Disk:** <1 MB

## Algorithm

```
Input: similarity matrix W (n×n), initial label matrix Y (n×C with labelled rows one-hot, unlabelled rows 0),
       damping α ∈ (0,1), iterations T
Output: label distribution F* over all n samples

Compute degree diagonal D; D_ii = Σ_j W_ij
Normalise:   S = D^{-1/2} · W · D^{-1/2}
Initialise:  F^{(0)} = Y
for t = 0..T-1:
    F^{(t+1)} = α · S · F^{(t)} + (1 − α) · Y
return F* = (1−α) · (I − α·S)^{-1} · Y     // closed form when converged
```

- **Paper update rule (Zhu/Ghahramani/Lafferty):** `F^{(t+1)} = α·S·F^{(t)} + (1−α)·Y` where S = D^{-1/2}·W·D^{-1/2} (normalised graph Laplacian); converges to `F* = (1−α)·(I − α·S)⁻¹·Y`
- **Time complexity:** O(T · nnz(W) · C) for iterative form
- **Space complexity:** O(n · C) for F + one scratch row

## Academic Source
Zhu, X., Ghahramani, Z. & Lafferty, J. (2003). "Semi-Supervised Learning Using Gaussian Fields and Harmonic Functions". ICML 2003, pp. 912-919. (Preceded by Zhou et al. 2004 on consistency; cited here per the assignment.)

## C++ Interface (pybind11)

```cpp
// Iterative power form on CSR sparse graph
std::vector<float> label_propagation(
    const int* csr_indptr, const int* csr_indices, const float* csr_data,
    int n_samples,
    const float* Y, int n_classes,     // initial labels (one-hot on labelled rows)
    float alpha, int max_iter, float tol
);
```

## Memory Budget
- Runtime RAM: <80 MB for n=1e5, C=10, nnz=1e7 (40 MB CSR + 4 MB F + 4 MB scratch)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: two `std::vector<float>` buffers size n·C, ping-pong

## Performance Target
- Python baseline: `scipy.sparse` CSR · dense multiply per iteration
- Target: ≥6x faster (SIMD inner loop, symmetric W half-store)
- Benchmark: 3 sizes — n=1e3/nnz=1e4, n=1e4/nnz=1e5, n=1e5/nnz=1e7

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Row-parallel SpMM via OpenMP; no shared row writes.

**Memory:** No raw `new`/`delete`. `reserve()` on ping-pong vectors. Bounds-checked in debug.

**Object lifetime:** Read-only CSR pointers; ping-pong ownership stays inside function.

**Type safety:** Explicit `static_cast` narrowing. Validate `α ∈ (0,1)`, `T ≥ 1`.

**SIMD:** AVX2 FMA on inner CSR accumulation. `_mm256_zeroupper()` on exit. `alignas(64)` on F rows.

**Floating point:** Double accumulator when C·avg_degree ≥ 1000. Clamp D_ii ≥ 1e-12 before D^{-1/2}.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Compressed CSR layout for cache.

**Error handling:** Destructors `noexcept`. Validate symmetric shape. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_188.py` | Matches sklearn LabelPropagation within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than scipy iteration |
| 5 | `pytest test_edges_meta_188.py` | Disconnected graph, α=0 (identity), α→1, zero-degree node |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP SpMM |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Graph comes from ANN index (META-15 neighbour cache) or cosine sparsification

## Pipeline Stage Non-Conflict
- **Owns:** Global label smoothing over similarity graph
- **Alternative to:** META-186 (local self-training), META-187 (co-training)
- **Coexists with:** META-184 (density-weighted) — both consume the same similarity graph

## Test Plan
- α=0: verify F* = Y identically
- Single connected component with one seed: verify all rows converge to the seed label
- Zero-degree isolated node: verify its row stays at Y (no propagation)
- Asymmetric W: verify raises ValueError
- Non-convergence within max_iter: verify returns best-effort F with warning flag
