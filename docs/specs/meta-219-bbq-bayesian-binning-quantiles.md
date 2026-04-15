# META-219 — BBQ (Bayesian Binning into Quantiles)

## Overview
**Category:** Probability calibration
**Extension file:** `bbq_calibration.cpp`
**Replaces/improves:** Single-binning histogram or isotonic calibration in `calibration.py`
**Expected speedup:** ≥6x over Python model-averaging loop
**RAM:** <20 MB | **Disk:** <1 MB

## Algorithm

Model-averaging across many binning models M, weighted by posterior P(M).

```
Input: scores s ∈ [0,1]^n, binary labels y ∈ {0,1}^n
Output: calibrator g(s) giving P(y=1 | s)

1. Enumerate binning models M_k with k ∈ {2..√n} equal-frequency bins
2. For each M_k:
     prior P(M_k) ∝ 1/k                              (simpler model preferred)
     for each bin b:
         likelihood via Beta-Binomial: P(data|M_k,b)
     P(data|M_k) = Π_b P(data|M_k,b)
3. Posterior P(M_k|data) ∝ P(data|M_k) · P(M_k)
4. Calibrated score:
     P(y|s) = Σ_k P(M_k|data) · P(y|s, M_k)
```

- **Time complexity:** O(K · n · log n) where K = √n distinct binnings
- **Space complexity:** O(K · B_max) for bin counts + posteriors
- **Convergence:** Bayesian — no iteration; closed-form Beta-Binomial marginal likelihood

## C++ Interface (pybind11)

```cpp
// Fit BBQ calibrator and return calibrated probabilities
std::vector<float> bbq_fit_predict(
    const float* scores, const int* labels, int n,
    const float* query_scores, int m,
    int min_bins, int max_bins,
    float alpha_prior, float beta_prior
);
```

## Memory Budget
- Runtime RAM: <20 MB (K binning models × bin stats)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(K * max_bins)`

## Performance Target
- Python baseline: nested loop over K binnings in `sklearn`-style fit loop
- Target: ≥6x faster (single pass, vectorized bin-count reduction)
- Benchmark: n ∈ {1k, 10k, 100k} scored examples × 20 binning models

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough` (see `backend/extensions/CPP-RULES.md`)

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for log-likelihood sums. Use `std::lgamma` for Beta-Binomial.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_219.py` | ECE within 1e-3 of Python reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python reference |
| 5 | `pytest test_edges_meta_219.py` | n=1, all-zero labels, all-one labels, NaN scores pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone calibrator; consumes raw scores + labels)

## Pipeline Stage & Non-Conflict
- **Stage:** Post-scoring calibration (after ranker, before threshold application)
- **Owns:** Bayesian model-averaged probability estimates
- **Alternative to:** META-04x Platt scaling, isotonic regression, temperature scaling
- **Coexists with:** Reliability diagram diagnostics (META-216), threshold tuning (META-217)

## Test Plan
- Perfectly calibrated input: verify calibrator ≈ identity (ECE < 0.01)
- Overconfident input (scores 0.9, base rate 0.5): verify calibrator pulls toward 0.5
- Single-bin edge: verify posterior concentrates on k=2 model
- Reliability diagram before/after: verify monotone improvement on synthetic miscalibration
