# META-166 — Akaike Information Criterion

## Overview
**Category:** Likelihood-based model selector
**Extension file:** `aic_selector.cpp`
**Replaces/improves:** Hand-rolled AIC expression in `ranking_calibration.py`
**Expected speedup:** ≥5x over Python loop for large candidate pools
**RAM:** <5 MB | **Disk:** <1 MB

## Algorithm

```
Input: maximum log-likelihoods {log L_k}, parameter counts {p_k}
Output: k* = argmin AIC_k

AIC_k = 2·p_k − 2·log L_k
return argmin_k AIC_k and AIC vector
```

- **Time complexity:** O(K)
- **Space complexity:** O(K)
- **Convergence:** Single-pass; efficient (minimises KL risk asymptotically)

## Academic Source
Akaike H., "A new look at the statistical model identification," *IEEE Transactions on Automatic Control* 19(6):716–723, 1974. DOI: 10.1109/TAC.1974.1100705

## C++ Interface (pybind11)

```cpp
// Return index of min AIC and write full AIC vector
int aic_select(
    const float* log_likelihoods, int n_models,
    const int* param_counts,
    float* out_aic
);
```

## Memory Budget
- Runtime RAM: <5 MB (AIC vector only)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` with `reserve(n_models)`

## Performance Target
- Python baseline: NumPy elementwise op in `model_selection.py`
- Target: ≥5x faster for n_models=200
- Benchmark: n_models ∈ {20, 200, 2000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch.

**SIMD:** `alignas(64)` on hot arrays. AVX2 fused-multiply-add for AIC compute.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on log L. Reject `p_k < 0`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_166.py` | Matches `statsmodels` AIC within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_166.py` | Ties, NaN log L, zero params all handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone selector)

## Pipeline Stage Non-Conflict
- **Owns:** AIC-based model ranking.
- **Alternative to:** META-165 (MDL), META-167 (BIC) — exactly one criterion chosen per experiment.
- **Coexists with:** META-177 (SHAP) for post-hoc explanation; AIC affects selection, not ranking output.
- No conflict with online ranker: runs only in offline calibration.

## Test Plan
- Overfitted model has higher AIC than parsimonious model on held-out data
- Equal log L: verify lower-parameter model wins
- Tied AIC: verify lowest-index returned deterministically
- Negative param count: verify raises ValueError
- NaN log L: verify raises ValueError
