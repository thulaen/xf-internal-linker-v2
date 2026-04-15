# META-90 — Histogram Binning Calibration

## Overview
**Category:** Non-parametric score calibrator (P9 calibration block)
**Extension file:** `histogram_binning.cpp`
**Replaces/improves:** Parametric Platt/Beta calibration when score-to-probability map has irregular shape — histogram binning makes no functional-form assumption
**Expected speedup:** ≥10x over Python loop-based binning
**RAM:** <2 MB | **Disk:** <1 MB

## Algorithm

```
Input: scores s_i ∈ ℝ, labels y_i ∈ {0,1}, n samples; bin count M
Output: piecewise-constant calibrator P(y=1 | s)

1. Sort scores ascending: s_(1) ≤ s_(2) ≤ … ≤ s_(n)
2. Partition into M bins:
     - Equal-frequency: bin_m contains floor(n/M) consecutive samples
     - (Alternative: equal-width over [min, max])
3. For each bin m:
     edges:        e_m = (s_(start), s_(end))
     calibrated:   p_m = (Σ_{i in bin_m} y_i) / |bin_m|       (empirical positive rate)
4. At inference: locate bin via binary search on edges, return p_bin

Optional: Laplace smoothing
     p_m = (1 + Σ y_i) / (2 + |bin_m|)        (paper Section 4)
```

- **Time complexity:** O(n log n) sort at fit, O(log M) per inference query
- **Space complexity:** O(M) for edges and probabilities
- **Convergence:** Exact in one pass (no iteration); larger M → finer resolution but lower per-bin sample size

## Academic source
Zadrozny, B. and Elkan, C., "Obtaining Calibrated Probability Estimates from Decision Trees and Naive Bayesian Classifiers", *Proceedings of the Eighteenth International Conference on Machine Learning (ICML)*, pp. 609–616, 2001.

## C++ Interface (pybind11)

```cpp
// Fit histogram binning calibrator
struct HistCalib { std::vector<float> edges; std::vector<float> probs; };

HistCalib hist_fit(
    const float* scores, const int* labels, int n,
    int n_bins, bool equal_frequency = true, bool laplace_smoothing = false
);

// Apply (binary search + lookup)
void hist_apply(
    const float* scores, int n,
    const float* edges, const float* probs, int n_bins,
    float* probs_out
);
```

## Memory Budget
- Runtime RAM: <2 MB (sort scratch + bin tables; sort is the dominant cost)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: in-place sort, fixed-size edges/probs vectors

## Performance Target
- Python baseline: NumPy `np.digitize` + `np.bincount` loop
- Target: ≥10x faster on n=1e6 (avoids Python boxing per bucket)
- Benchmark: 3 sizes — n ∈ {1e3, 1e5, 1e6}, M = 20

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Sort uses `std::sort` on a thread-local index vector — never on the caller's data in place.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled. Validate labels ∈ {0,1}; validate n_bins ≥ 1 and ≤ n.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays. `hist_apply` binary-search loop is scalar (data-dependent branches).

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for positive-count sums (although ints used internally).

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. NaN scores at fit time raise; at inference time return NaN cleanly.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

Adheres to `backend/extensions/CPP-RULES.md` in full.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_90.py` | Bin probs match Python reference exactly (integer ratios) |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `pytest backend/benchmarks/test_bench_histogram.py` | ≥10x speedup on 3 sizes |
| 5 | `pytest test_edges_meta_90.py` | n_bins=1 (constant), n_bins=n (per-sample), all-positive, all-negative, NaN scores handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | ECE check | Post-calibration ECE ≤ pre-calibration ECE on test set |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- pybind11 ≥ 2.10
- No external deps; uses only `std::sort`

## Pipeline stage non-conflict declaration
- **Owns:** Equal-frequency / equal-width binning + per-bin empirical positive rate
- **Alternative to:** META-87 Platt (parametric), META-88 Beta (parametric), META-89 Dirichlet (multiclass parametric)
- **Coexists with:** All P8 regularisers, all P10 LR schedulers; histogram binning is post-hoc only

## Test Plan
- Synthetic data with known piecewise-constant true calibration: verify recovery
- n_bins = 1: returns global positive rate for all queries
- n_bins = n: each bin has one sample, p_m = label_i (highest variance)
- Equal-frequency vs equal-width: verify both work and produce sane outputs
- Laplace smoothing: verify off-by-1 numerator/denominator and bounded probs ∈ (0,1)
