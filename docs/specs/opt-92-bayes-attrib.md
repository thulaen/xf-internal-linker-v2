# OPT-92 -- Bayesian Gamma-Poisson Attribution

## Overview
**Category:** C# native interop -- statistics
**Extension file:** `bayes_attrib.cpp` (NEW) + C# P/Invoke
**Expected speedup:** >=3x over C# MathNet.Numerics single-threaded Gamma-Poisson
**RAM:** <2 MB | **Disk:** <1 MB
**Research basis:** Gelman A. et al., "Bayesian Data Analysis", 3rd edition, CRC Press 2013. Gamma-Poisson conjugate model for count data attribution.

## Algorithm

Gamma-Poisson conjugate model: Prior Gamma(alpha, beta) + observed counts (clicks, impressions) -> Posterior Gamma(alpha + sum_clicks, beta + n_periods). Batch-vectorized: all keywords processed in one parallel pass. For each keyword: compute posterior mean (alpha+clicks)/(beta+periods), posterior variance, credible interval, and attribution score. TBB parallel_for over keywords.

## C++ Interface (exported as C function for P/Invoke)

```cpp
// bayes_attrib.cpp
// extern "C" int32_t cbayes_attrib(
//     const float* prior_alpha, const float* prior_beta,
//     const uint32_t* click_counts, const uint32_t* impression_counts,
//     uint32_t n_periods, uint32_t n_keywords,
//     float* out_posterior_mean, float* out_posterior_var,
//     float* out_ci_low, float* out_ci_high,
//     float* out_attribution_score);
```

## Memory Budget
- Runtime RAM: <2 MB (arrays for 10K keywords)
- Disk: <1 MB

## Performance Target
- Target: >=3x faster than C# MathNet.Numerics single-threaded Gamma-Poisson
- Benchmark: 10K keywords x 1000 iterations

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Predicate-form `condition_variable::wait()`. Document atomic ordering. `_mm_pause()` spinlocks with 1000-iter fallback.

**Memory:** No raw `new`/`delete` hot paths. No `alloca`/VLA. No `void*` delete. RAII only. Debug bounds checks. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view`. No `[&]` beyond scope. No return ref to local.

**Type safety:** `static_cast` for narrowing. No signed/unsigned mismatch. No aliasing violation. All switch handled.

**SIMD:** No SSE/AVX mix without `zeroupper`. Unaligned loads. Max 12 YMM. `alignas(64)` hot arrays.

**Floating point:** Flush-to-zero init. NaN/Inf entry checks. Double accumulator >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** `noexcept` destructors. `const&` catch. Basic guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_str)`. Scrub memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings `-Werror` |
| 2 | `pytest test_parity_*.py` | Matches Python ref within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero ASAN/UBSan errors |
| 4 | `bench_extensions.py` | >=3x faster than Python |
| 5 | `pytest test_edges_*.py` | Empty, single, NaN/Inf, n=10000 pass |
| 6 | `valgrind --leak-check=full` | Zero leaks |
| 7 | `TSAN=1 build + pytest` | Zero races |
| 8 | Human reviewer | CPP-RULES.md confirmed |

## Dependencies
- TBB (Linux) or std::execution::par (Windows)
- No external math library (Gamma function approximated via Stirling or lgamma from cmath)

## Test Plan
- Posterior parameters match MathNet.Numerics reference within 1e-4
- Edge cases: zero clicks, zero impressions, single keyword, prior alpha=0 (degenerate), very large counts
