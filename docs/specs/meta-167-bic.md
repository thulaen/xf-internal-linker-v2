# META-167 — Bayesian Information Criterion

## Overview
**Category:** Likelihood-based model selector
**Extension file:** `bic_selector.cpp`
**Replaces/improves:** Hand-rolled BIC loop in `ranking_calibration.py`
**Expected speedup:** ≥5x over Python loop for large candidate pools
**RAM:** <5 MB | **Disk:** <1 MB

## Algorithm

```
Input: maximum log-likelihoods {log L_k}, parameter counts {p_k}, n samples
Output: k* = argmin BIC_k

BIC_k = p_k · log(n) − 2 · log L_k
return argmin_k BIC_k and BIC vector
```

- **Time complexity:** O(K)
- **Space complexity:** O(K)
- **Convergence:** Single-pass; consistent — picks the true model with probability → 1 as n → ∞

## Academic Source
Schwarz G., "Estimating the dimension of a model," *Annals of Statistics* 6(2):461–464, 1978. DOI: 10.1214/aos/1176344136

## C++ Interface (pybind11)

```cpp
// Return index of min BIC and write full BIC vector
int bic_select(
    const float* log_likelihoods, int n_models,
    const int* param_counts,
    int n_samples,
    float* out_bic
);
```

## Memory Budget
- Runtime RAM: <5 MB (BIC vector only)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` with `reserve(n_models)`

## Performance Target
- Python baseline: NumPy elementwise op
- Target: ≥5x faster for n_models=200
- Benchmark: n_models ∈ {20, 200, 2000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. Arena/pool/RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** `alignas(64)` on hot arrays. FMA used for BIC compute.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on log L. Reject `n_samples ≤ 0` (cannot take `log(n)`).

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_167.py` | Matches `statsmodels` BIC within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_167.py` | n=1, ties, NaN log L all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone selector)

## Pipeline Stage Non-Conflict
- **Owns:** BIC-based model ranking.
- **Alternative to:** META-165 (MDL), META-166 (AIC) — exactly one criterion chosen per experiment.
- **Coexists with:** BIC reported alongside AIC/MDL in calibration reports for comparison.
- No conflict with online ranker: runs only in offline calibration.

## Test Plan
- Nested regressions: verify true model wins as n grows (consistency)
- n=1000 vs. n=10: BIC penalty growth behaves correctly
- Equal log L: verify lower-parameter model wins
- n_samples=0: verify raises ValueError
- NaN log L: verify raises ValueError
