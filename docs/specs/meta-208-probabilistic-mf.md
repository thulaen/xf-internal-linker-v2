# META-208 — Probabilistic Matrix Factorisation (PMF)

## Overview
**Category:** Matrix factorisation (probabilistic, MAP via SGD)
**Extension file:** `pmf.cpp`
**Replaces/improves:** Hand-rolled numpy SGD solver for user/item latent factors
**Expected speedup:** ≥10x over pure-Python SGD loop
**RAM:** <150 MB for 100k users × 50k items, k=32 | **Disk:** <1 MB

## Algorithm

```
Input:  observed ratings R_ij for (i,j) ∈ Ω, rank k
Priors: U_i ~ N(0, σ_U² · I)   U ∈ ℝ^{N×k}
        V_j ~ N(0, σ_V² · I)   V ∈ ℝ^{M×k}
Likelihood: R_ij ~ N(U_iᵀ V_j, σ²)

MAP objective (negative log-posterior, Salakhutdinov & Mnih Eq. 4):
  L = Σ_{(i,j) ∈ Ω} (R_ij − U_iᵀ V_j)²  +  λ_U ·‖U‖_F²  +  λ_V ·‖V‖_F²
  with λ_U = σ²/σ_U²,  λ_V = σ²/σ_V²

SGD per observation:
  e = R_ij − U_iᵀ V_j
  U_i ← U_i + η · (e · V_j − λ_U · U_i)
  V_j ← V_j + η · (e · U_i − λ_V · V_j)
```

- **Time complexity:** O(epochs · |Ω| · k)
- **Space complexity:** O((N + M) · k)
- **Convergence:** Non-convex; momentum SGD typically converges in 30–80 epochs on MovieLens-scale data

## Academic Source
Salakhutdinov, R. & Mnih, A. "Probabilistic Matrix Factorization." *Advances in Neural Information Processing Systems 20 (NIPS 2007)*, 1257–1264, published 2008. DOI: 10.5555/2981562.2981720.

## C++ Interface (pybind11)

```cpp
// MAP PMF via SGD with momentum; returns (U, V) factor matrices
std::tuple<py::array_t<float>, py::array_t<float>>
pmf_map_sgd(
    py::array_t<int32_t>  row_idx,      // length |Omega|
    py::array_t<int32_t>  col_idx,      // length |Omega|
    py::array_t<float>    ratings,      // length |Omega|
    int N, int M, int k,
    int epochs = 60, float lr = 0.01f, float momentum = 0.9f,
    float lambda_U = 0.02f, float lambda_V = 0.02f,
    uint64_t seed = 0
);
```

## Memory Budget
- Runtime RAM: <150 MB at N=100000, M=50000, k=32 (U, V, momentum buffers)
- Disk: <1 MB (compiled .so/.pyd)
- Allocation: `reserve((N+M)*k)` up-front; zero allocation inside epoch loop

## Performance Target
- Baseline: numpy SGD loop over observations (Python-level `for`)
- Target: ≥10x faster end-to-end epoch time at 1M observations
- Benchmark: 3 sizes — (1k×1k, |Ω|=50k, k=8), (10k×5k, |Ω|=500k, k=16), (100k×50k, |Ω|=5M, k=32)

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`. Full list per `backend/extensions/CPP-RULES.md`.

**Threading:** HOGWILD-style parallel SGD across observations; documented `memory_order_relaxed` on factor updates. No `std::recursive_mutex`. No `volatile`.

**Memory:** No raw `new`/`delete` in hot path. Arena for per-thread RNG state. Bounds-checked `row_idx[t] < N` and `col_idx[t] < M` in debug.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for int32→size_t. No signed/unsigned mismatch.

**SIMD:** Dot product U_iᵀ V_j vectorised with AVX2 at k ≥ 8. `_mm256_zeroupper()` before return. `alignas(64)` on rows.

**Floating point:** Double accumulator for NDCG eval. Clamp gradient to [−1e3, +1e3] to prevent Inf blow-up. NaN rating rejected at entry.

**Performance:** No `std::endl` in epoch log (caller prints). No `std::function`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Raise `py::value_error` on NaN rating or out-of-range index.

**Build:** No cyclic includes. Anonymous namespace for internal RNG.

**Security:** No `system()`. Seed path does not read `/dev/random` implicitly.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_208.py` | Test RMSE within 2% of numpy reference at seed-matched run |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥10x faster than Python SGD at all 3 sizes |
| 5 | `pytest test_edges_meta_208.py` | Empty Ω, k=1, NaN rating, oob index all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races beyond documented HOGWILD relaxations |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone). May be warm-started from META-206 (SVD) output.

## Pipeline Stage Non-Conflict
- **Stage owned:** Offline latent factor learning over observed rating/engagement matrix
- **Owns:** MAP estimate of (U, V) via SGD
- **Alternative to:** META-209 (Bayesian PMF — full posterior), META-210 (WALS — implicit-feedback ALS)
- **Coexists with:** META-206 (SVD can seed PMF init)

## Test Plan
- Synthetic low-rank R = U₀ V₀ᵀ + noise: verify recovered RMSE ≤ noise σ + 10%
- Empty Ω: verify raises `py::value_error`
- Single observation: verify U_i, V_j updated, others stay at prior mean
- NaN rating: verify rejection
- Reproducibility: same seed → same RMSE to 1e-5 on same hardware
