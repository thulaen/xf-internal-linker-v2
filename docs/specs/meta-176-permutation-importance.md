# META-176 — Permutation Importance

## Overview
**Category:** Model-agnostic feature attribution
**Extension file:** `permutation_importance.cpp`
**Replaces/improves:** `sklearn.inspection.permutation_importance` Python loop in `diagnostics.py`
**Expected speedup:** ≥8x over sklearn for N=10k, features=50, n_repeats=30
**RAM:** <100 MB | **Disk:** <1 MB

## Algorithm

```
Input: data X ∈ ℝ^{N×d}, targets y, model f, scorer s, n_repeats R
Output: importance vector imp ∈ ℝ^d

baseline = s(f, X, y)
for j = 1..d:
    drops = []
    for r = 1..R:
        X' = X with column j permuted (Fisher–Yates, fresh seed)
        drops.append( baseline − s(f, X', y) )
    imp_j = mean(drops); std_j = stdev(drops)
```

- **Time complexity:** O(d · R · eval_cost)
- **Space complexity:** O(N·d) for the permuted-column scratch buffer
- **Convergence:** Monte-Carlo; standard error ∝ 1/√R

## Academic Source
Breiman L., "Random forests," *Machine Learning* 45(1):5–32, 2001. DOI: 10.1023/A:1010933404324

## C++ Interface (pybind11)

```cpp
// Permutation importance calling back into Python scorer via pybind11 std::function
void permutation_importance(
    const float* X, int N, int d,
    const float* y,
    std::function<float(const float*, int, int, const float*)> scorer,
    int n_repeats, uint64_t seed,
    float* out_importance_mean, float* out_importance_std
);
```

## Memory Budget
- Runtime RAM: <100 MB for N=10k, d=50 (one row-major column copy + PRNG state)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: one `std::vector<float>` scratch column, `reserve(N)` once

## Performance Target
- Python baseline: `sklearn.inspection.permutation_importance(n_repeats=30)`
- Target: ≥8x faster for N=10k, d=50, R=30
- Benchmark: N ∈ {1k, 10k, 100k}, d ∈ {10, 50, 200}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. Repeats may be parallelised; each thread gets its own PRNG seeded from a master `std::seed_seq`. Scorer callbacks must be thread-safe (documented in signature).

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. Arena/pool/RAII only. `reserve()` before fills.

**Object lifetime:** Self-assignment safe. No dangling capture of X in scorer closure. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch on indices.

**SIMD:** `alignas(64)` on scratch columns. Fisher–Yates uses SIMD-unfriendly scalar loop — accept; permutation is bandwidth-bound.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on X, y. Double accumulator for mean/stdev of drops.

**Performance:** No `std::endl` loops. **Warning:** `std::function` scorer is unavoidable here — document and exclude from the "no `std::function` in hot loops" rule with explicit justification in the header.

**Error handling:** Destructors `noexcept`. Catch `const&`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. Scrub sensitive memory. PRNG seed logged but never exposed.

Full rules: see `backend/extensions/CPP-RULES.md`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_176.py` | Matches sklearn means within 2·std error |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than sklearn |
| 5 | `pytest test_edges_meta_176.py` | Constant feature, perfectly correlated features, d=1 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races in parallel repeats |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (uses user-provided Python scorer)

## Pipeline Stage Non-Conflict
- **Owns:** Model-agnostic permutation-based feature importance reports.
- **Alternative to:** META-180 (MDI, tree-specific), META-177 (SHAP), META-178 (LIME) — different lenses.
- **Coexists with:** Diagnostics dashboard (`/performance` and `/diagnostics`) consumes this output.
- No conflict with ranking: attribution runs offline and reports only; does not mutate weights.

## Test Plan
- Constant feature: importance ≈ 0 ± SE
- Perfectly informative feature: positive importance clearly above SE band
- Two highly correlated features: verify both show reduced individual importance (bias documented)
- Reproducibility: fixed seed produces bit-identical results single-threaded
- NaN target: verify raises ValueError
