# META-191 — Inverse Propensity Weighting (IPW)

## Overview
**Category:** Causal inference (reweighting observational data)
**Extension file:** `ipw.cpp`
**Replaces/improves:** Naive ATE estimate via difference-in-means when treatment is confounded
**Expected speedup:** ≥6x over Python sklearn propensity + numpy reduction
**RAM:** <8 MB | **Disk:** <1 MB

## Algorithm

```
Input: n samples (X_i, T_i, Y_i); propensity π̂(X) = P(T=1 | X)
Output: potential-outcome estimates Ê[Y(1)], Ê[Y(0)], ATE

Clip propensities:  π̂_i ← clip(π̂_i, ε, 1 − ε)

Ê[Y(1)] = (1/n) · Σ_i  T_i · Y_i / π̂_i
Ê[Y(0)] = (1/n) · Σ_i  (1 − T_i) · Y_i / (1 − π̂_i)
ATE    = Ê[Y(1)] − Ê[Y(0)]
```

- **Paper update rule (Rosenbaum & Rubin):** `E[Y(1)] = E[T·Y / π(X)]`, `E[Y(0)] = E[(1−T)·Y / (1−π(X))]` where π(X) = P(T=1|X)
- **Time complexity:** O(n) reduction
- **Space complexity:** O(1) scalar accumulators (no allocation proportional to n)

## Academic Source
Rosenbaum, P. R. & Rubin, D. B. (1983). "The Central Role of the Propensity Score in Observational Studies for Causal Effects". Biometrika, Vol. 70, No. 1, pp. 41-55. DOI: 10.1093/biomet/70.1.41

## C++ Interface (pybind11)

```cpp
struct IpwResult { double ey1; double ey0; double ate; double ess1; double ess0; };
IpwResult ipw_estimate(
    const uint8_t* treatment,   // [n] 0/1
    const float* outcome,       // [n]
    const float* propensity,    // [n]
    int n, float eps_clip       // default 1e-3
);
```

## Memory Budget
- Runtime RAM: <8 MB (O(1) accumulators)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: none beyond the returned struct

## Performance Target
- Python baseline: `np.sum(T·Y / π) / n` with clip + mask
- Target: ≥6x faster via AVX2 FMA reduction + Kahan compensation
- Benchmark: 3 sizes — n=1e3, n=1e5, n=1e7

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** OpenMP reduction over sum; scalar outputs.

**Memory:** No raw `new`/`delete`. No allocation in hot path.

**Object lifetime:** Read-only input pointers.

**Type safety:** Explicit `static_cast` narrowing. Validate `T ∈ {0,1}` in debug.

**SIMD:** AVX2 FMA with double accumulator. `_mm256_zeroupper()` on exit. Kahan compensation for n ≥ 1e6.

**Floating point:** Double accumulator mandatory. Clip π to [ε, 1−ε] with ε ≥ 1e-6. NaN/Inf entry checks.

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Single pass over data.

**Error handling:** Destructors `noexcept`. Validate `0 < ε < 0.5`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_191.py` | Matches DoWhy/EconML IPW within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than numpy reference |
| 5 | `pytest test_edges_meta_191.py` | π=0, π=1, all T=0, all T=1, NaN outcome |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP reduction |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Caller supplies propensity vector (logistic-regression fit, or META-194 causal forest partial)

## Pipeline Stage Non-Conflict
- **Owns:** Horvitz–Thompson-style weighted mean of outcomes
- **Alternative to:** Plain mean diff (no correction), META-193 (doubly robust)
- **Coexists with:** META-192 (DML) — DML uses IPW-style orthogonalisation in the numerator

## Test Plan
- π ≡ 0.5: verify ATE ≈ mean(Y|T=1) − mean(Y|T=0) (no correction needed)
- All T=1: verify `ey0 = 0` with ESS_0 = 0 flag
- Perfectly randomised: verify ATE matches naive diff within MC noise
- Extreme π near 0: verify clipping engaged; no Inf
- NaN in outcome: verify raises ValueError
