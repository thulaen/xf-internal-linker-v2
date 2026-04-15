# META-193 — Doubly Robust Estimator

## Overview
**Category:** Causal inference (augmented IPW / AIPW)
**Extension file:** `doubly_robust.cpp`
**Replaces/improves:** IPW (META-191) — consistent if EITHER propensity OR outcome model is correct
**Expected speedup:** ≥6x over Python AIPW numpy formula
**RAM:** <16 MB | **Disk:** <1 MB

## Algorithm

```
Input: n samples (X_i, T_i, Y_i), outcome models m̂(1,X), m̂(0,X), propensity ê(X)
Output: per-sample pseudo-outcome τ̂_DR(x) for CATE estimation; population ATE via mean

Clip propensities:  ê_i ← clip(ê_i, ε, 1 − ε)

for each i:
    τ̂_DR(x_i) = m̂(1, x_i) − m̂(0, x_i)
               + T_i     · (Y_i − m̂(1, x_i)) / ê_i
               − (1−T_i) · (Y_i − m̂(0, x_i)) / (1 − ê_i)

ATE_DR = (1/n) · Σ_i τ̂_DR(x_i)
```

- **Paper update rule (Bang & Robins):** `τ̂_DR(x) = m̂(1,x) − m̂(0,x) + T·(Y − m̂(1,x))/ê(x) − (1−T)·(Y − m̂(0,x))/(1 − ê(x))`
- **Time complexity:** O(n) reduction
- **Space complexity:** O(n) if per-sample pseudo-outcome returned; O(1) for ATE-only

## Academic Source
Bang, H. & Robins, J. M. (2005). "Doubly Robust Estimation in Missing Data and Causal Inference Models". Biometrics, Vol. 61, No. 4, pp. 962-973. DOI: 10.1111/j.1541-0420.2005.00377.x

## C++ Interface (pybind11)

```cpp
struct DrResult { std::vector<float> tau_dr; double ate; double se; };
DrResult doubly_robust(
    const uint8_t* treatment,  // [n]
    const float* outcome,      // [n]
    const float* m_hat_1,      // [n]  m̂(1, X_i)
    const float* m_hat_0,      // [n]  m̂(0, X_i)
    const float* e_hat,        // [n]  ê(X_i)
    int n, float eps_clip
);
```

## Memory Budget
- Runtime RAM: <16 MB for n=1e6 (4 MB τ̂_DR output + scratch)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` `reserve(n)`

## Performance Target
- Python baseline: vectorised numpy AIPW formula
- Target: ≥6x faster via fused SIMD FMA pass
- Benchmark: 3 sizes — n=1e3, n=1e5, n=1e7

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** OpenMP parallel over samples; `tau_dr[i]` writes independent.

**Memory:** No raw `new`/`delete`. `reserve()` on output. Bounds-checked in debug.

**Object lifetime:** Read-only input pointers; output struct owns `tau_dr`.

**Type safety:** Explicit `static_cast` narrowing. Validate `T ∈ {0,1}`.

**SIMD:** AVX2 FMA for residual terms; `_mm256_zeroupper()` on exit. `alignas(64)` buffers.

**Floating point:** Double accumulator for ATE. Clip ê ∈ [ε, 1−ε] with ε ≥ 1e-6. NaN/Inf entry checks.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Fused single pass.

**Error handling:** Destructors `noexcept`. Validate all input shapes equal. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_193.py` | Matches EconML DRLearner within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than numpy reference |
| 5 | `pytest test_edges_meta_193.py` | ê near 0/1 (clipping), constant m̂, n=1 |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller provides nuisance predictions `m̂(1, ·)`, `m̂(0, ·)`, `ê(·)`

## Pipeline Stage Non-Conflict
- **Owns:** Per-sample AIPW pseudo-outcome + ATE
- **Alternative to:** META-191 (IPW only), META-192 (DML linear)
- **Coexists with:** META-195 (meta-learner family) — DR pseudo-outcome feeds X-learner second stage

## Test Plan
- Randomised trial (ê = 0.5): verify DR ≈ difference-in-means + small correction
- Perfect m̂ (residual = 0): verify DR = m̂(1) − m̂(0) per sample
- Perfect ê but wrong m̂: verify population ATE still consistent (double robustness)
- ê near boundary: verify clipping engaged, no NaN in output
- NaN in any input: verify raises ValueError
