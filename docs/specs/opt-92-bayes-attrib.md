# OPT-92 -- Bayesian Gamma-Poisson Attribution

## Overview
**Category:** Python pybind11 native extension -- statistics
**Extension file:** `backend/extensions/bayes_attrib.cpp` (NEW) + pybind11 module bindings
**Expected speedup:** >=3x over a single-threaded `scipy.stats` Gamma-Poisson Python reference
**RAM:** <2 MB | **Disk:** <1 MB
**Research basis:** Gelman A. et al., "Bayesian Data Analysis", 3rd edition, CRC Press 2013. Gamma-Poisson conjugate model for count data attribution.

> **Provenance note (2026-04-26):** Originally written for the C# HttpWorker era when this extension would have been called from C# via P/Invoke and benchmarked against `MathNet.Numerics`. After the 2026-04 C# decommission, the extension is a pybind11 module called from Python and benchmarked against a `scipy.stats` reference. The math is unchanged — `scipy.stats.gamma` and `numpy.random.Generator.poisson` give the same posterior parameters as `MathNet.Numerics.Distributions.Gamma` to within numerical precision.

## Algorithm

Gamma-Poisson conjugate model: Prior Gamma(alpha, beta) + observed counts (clicks, impressions) -> Posterior Gamma(alpha + sum_clicks, beta + n_periods). Batch-vectorized: all keywords processed in one parallel pass. For each keyword: compute posterior mean (alpha+clicks)/(beta+periods), posterior variance, credible interval, and attribution score. TBB parallel_for over keywords.

## C++ Interface (pybind11)

```cpp
// bayes_attrib.cpp — exported as a pybind11 module function
// PYBIND11_MODULE(bayes_attrib, m) {
//     m.def("attribute_batch",
//         [](py::array_t<float> prior_alpha, py::array_t<float> prior_beta,
//            py::array_t<uint32_t> click_counts, py::array_t<uint32_t> impression_counts,
//            uint32_t n_periods)
//         -> py::dict { /* returns {posterior_mean, posterior_var, ci_low, ci_high, attribution_score} */ });
// }
```

## Memory Budget
- Runtime RAM: <2 MB (arrays for 10K keywords)
- Disk: <1 MB

## Performance Target
- Target: >=3x faster than a single-threaded `scipy.stats` Gamma-Poisson Python reference
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
- Posterior parameters match the `scipy.stats` Python reference within 1e-4 — see `backend/tests/test_parity_bayes_attrib.py`
- Edge cases: zero clicks, zero impressions, single keyword, prior alpha=0 (degenerate), very large counts
