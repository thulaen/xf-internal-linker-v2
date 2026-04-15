# META-181 — Uncertainty Sampling

## Overview
**Category:** Active learning query strategy
**Extension file:** `uncertainty_sampling.cpp`
**Replaces/improves:** Random sampling for human-in-the-loop link labelling
**Expected speedup:** ≥8x over Python numpy argmax/entropy scan per unlabeled pool
**RAM:** <12 MB | **Disk:** <1 MB

## Algorithm

```
Input: unlabeled pool U = {x_1..x_N}, probabilistic classifier P(y|x), strategy ∈ {lc, entropy}
Output: next query x* to send to the human labeler

for each x in U:
    p_y = P(y|x)                         // C-class posterior vector
    if strategy == "lc":                 // least confident
        score(x) = 1 − max_y p_y
    elif strategy == "entropy":
        score(x) = − Σ_y p_y · log(p_y)

x* = argmax_{x in U} score(x)
```

- **Paper update rule (Lewis & Catlett):** select `x* = argmax_x (1 − max_y P(y|x))` (least confident) or `argmax_x H(Y|x)` (entropy)
- **Time complexity:** O(|U| · C) per query
- **Space complexity:** O(|U|) for score buffer

## Academic Source
Lewis, D. D. & Catlett, J. (1994). "Heterogeneous Uncertainty Sampling for Supervised Learning". ICML 1994, pp. 148-156. DOI: 10.1016/B978-1-55860-335-6.50026-X

## C++ Interface (pybind11)

```cpp
// Return indices into probs_matrix sorted by uncertainty score (descending)
std::vector<int> uncertainty_sampling(
    const float* probs_matrix, int n_samples, int n_classes,
    const char* strategy,   // "lc" or "entropy"
    int top_k
);
```

## Memory Budget
- Runtime RAM: <12 MB for |U|=1e6 at C=10 (40 MB probs + 4 MB scores)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: single `std::vector<float>` scratch via `reserve(n_samples)`

## Performance Target
- Python baseline: `numpy.argmax` + `scipy.stats.entropy` loop
- Target: ≥8x faster (tight SIMD log reduction)
- Benchmark: 3 sizes — |U|=1e3, 1e5, 1e6 at C=10

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** No mutex needed (read-only scan). No `volatile`. No detached threads.

**Memory:** No raw `new`/`delete`. Arena/RAII only. Bounds-checked in debug. `reserve()` before fills.

**Object lifetime:** No dangling `string_view`. No `[&]` capture beyond scope.

**Type safety:** Explicit `static_cast` for narrowing. No signed/unsigned mismatch.

**SIMD:** AVX2 log via `_mm256_log_ps` polynomial; `_mm256_zeroupper()` on exit. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. Clamp probs to [1e-12, 1] before log. NaN/Inf entry checks.

**Performance:** No `std::function` hot loops. No `dynamic_cast`.

**Error handling:** Destructors `noexcept`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_181.py` | Matches sklearn.modAL within 1e-5 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥8x faster than Python reference |
| 5 | `pytest test_edges_meta_181.py` | Empty, uniform probs, one-hot, NaN all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | N/A (single-threaded read-only) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone query selector)

## Pipeline Stage Non-Conflict
- **Owns:** Query point selection for human labelling queue
- **Alternative to:** META-182 (QBC), META-183 (EMC), META-184 (density-weighted)
- **Coexists with:** All ranking metas (META-01..META-10), attribution metas

## Test Plan
- 2-class uniform (p=0.5): verify score = 0.5 (lc) and log(2) (entropy)
- 2-class one-hot: verify score = 0 both strategies
- 10-class uniform: verify entropy = log(10)
- NaN/Inf probs: verify raises ValueError
- |U|=0 empty pool: verify returns empty vector
