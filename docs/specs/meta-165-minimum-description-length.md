# META-165 — Minimum Description Length Selector

## Overview
**Category:** Information-theoretic model selector
**Extension file:** `mdl_selector.cpp`
**Replaces/improves:** Manual model-capacity choices in `ranking_calibration.py`
**Expected speedup:** ≥5x over Python bit-cost scoring
**RAM:** <10 MB | **Disk:** <1 MB

## Algorithm

```
Input: candidate models {M_k}, data D
Output: k* = argmin_k [ L(M_k) + L(D | M_k) ]      (bits)

L(M_k)     = (p_k/2)·log₂(n) + param_precision_bits   # two-part code
L(D | M_k) = −Σ_i log₂ P̂(d_i | M_k)                  # NLL in bits

pick k* with minimum total description length
```

- **Time complexity:** O(K · n) where K = candidate count
- **Space complexity:** O(K)
- **Convergence:** Deterministic single pass; consistent for true model in the limit

## Academic Source
Rissanen J., "Modeling by shortest data description," *Automatica* 14(5):465–471, 1978. DOI: 10.1016/0005-1098(78)90005-5

## C++ Interface (pybind11)

```cpp
// Return index of the minimum-description-length model and total bits vector
int mdl_select(
    const float* neg_log_likelihoods_bits, int n_models,
    const int* param_counts,
    int n_samples,
    float* out_total_bits
);
```

## Memory Budget
- Runtime RAM: <10 MB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` sized to `n_models`

## Performance Target
- Python baseline: for-loop in `model_selection.py`
- Target: ≥5x faster for n_models=50
- Benchmark: n_models ∈ {10, 50, 200}, n_samples ∈ {1k, 10k}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Base-2 log via `log2f`; double accumulator for NLL sums. Reject `n_samples ≤ 0`.

**Performance:** No `std::endl` loops. No `std::function` hot loops. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_165.py` | Matches Python bit-cost reference within 1e-6 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥5x faster than Python reference |
| 5 | `pytest test_edges_meta_165.py` | Single model, zero params, tied scores handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone selector)

## Pipeline Stage Non-Conflict
- **Owns:** Bit-cost model selection across calibration candidates.
- **Alternative to:** META-166 (AIC), META-167 (BIC) — user picks one criterion per experiment.
- **Coexists with:** Cross-validation harness (MDL is a complement, not replacement).
- No conflict with ranking: used only in offline calibration reports.

## Test Plan
- Nested polynomial regression: verify true degree is picked as n grows
- Constant model vs. linear: verify correct pick for noise-only data
- Tied bits: verify lowest-index model returned deterministically
- Zero params: verify treated as L(M)=0
- Invalid n_samples: verify raises ValueError
