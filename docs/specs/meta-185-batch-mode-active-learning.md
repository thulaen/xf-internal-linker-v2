# META-185 — Batch-Mode Active Learning

## Overview
**Category:** Active learning batch-selector (submodular greedy)
**Extension file:** `batch_mode_al.cpp`
**Replaces/improves:** Sequentially re-training per label (META-181..184 select only one point at a time)
**Expected speedup:** ≥6x over Python greedy submodular loop
**RAM:** <48 MB | **Disk:** <1 MB

## Algorithm

```
Input: pool U, per-point uncertainty u(x), pairwise similarity sim, batch size B, redundancy λ
Output: batch S ⊂ U, |S| = B, maximising uncertainty − λ·redundancy

S ← ∅
while |S| < B:
    for each x in U \ S:
        gain(x) = u(x) − λ · max_{x' in S} sim(x, x')     // marginal submodular gain
    x* = argmax_{x in U \ S} gain(x)
    S ← S ∪ {x*}
return S
```

- **Paper update rule (Hoi et al.):** select batch B to maximize `uncertainty(B) − λ·redundancy(B)` via submodular greedy
- **Time complexity:** O(B · |U|) with caching of current max-sim per candidate
- **Space complexity:** O(|U|) max-sim cache + O(B) selected indices

## Academic Source
Hoi, S. C. H., Jin, R., Zhu, J. & Lyu, M. R. (2006). "Batch Mode Active Learning and Its Application to Medical Image Classification". ICML 2006, pp. 417-424. DOI: 10.1145/1143844.1143897

## C++ Interface (pybind11)

```cpp
// Greedy submodular batch selection with lazy max-sim cache
std::vector<int> batch_mode_al(
    const float* uncertainty,   // [n_samples]
    const float* sim_matrix,    // [n_samples, n_samples]
    int n_samples, int batch_size, float lambda
);
```

## Memory Budget
- Runtime RAM: <48 MB — max-sim cache O(|U|) + sim_matrix pointer; |U|=3000 dense fits
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector<float>` max_sim `reserve(n_samples)`; `std::vector<int>` selected `reserve(B)`

## Performance Target
- Python baseline: pure-Python greedy loop with numpy pairwise max
- Target: ≥6x faster (SIMD max-update over unselected mask)
- Benchmark: 3 sizes — |U|=500/B=20, |U|=2000/B=50, |U|=3000/B=100

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

See `backend/extensions/CPP-RULES.md` for full mandate.

**Threading:** Inner gain loop parallel via OpenMP reduction on argmax.

**Memory:** No raw `new`/`delete`. `reserve()` before fills. Bounds-checked in debug.

**Object lifetime:** Read-only sim_matrix pointer; no dangling refs across iterations.

**Type safety:** Explicit `static_cast` narrowing. `batch_size ≤ n_samples` validated.

**SIMD:** AVX2 `_mm256_max_ps` for max-sim update pass. `_mm256_zeroupper()` on exit. `alignas(64)` on caches.

**Floating point:** Flush-to-zero. `λ ≥ 0` validated. Double accumulator not needed (elementwise max).

**Performance:** No `std::function` hot loops. No `dynamic_cast`. Bit-packed selected-mask for branchless gain.

**Error handling:** Destructors `noexcept`. Validate `B ≥ 1`. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace.

**Security:** No `system()`. No `printf(user_string)`.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_185.py` | Same batch as Python greedy within tie-break tolerance |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥6x faster than Python greedy |
| 5 | `pytest test_edges_meta_185.py` | B=1, B=|U|, λ=0 (pure uncertainty), all-identical |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races with OMP reduction |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Consumes per-point scores from META-181, META-183, or META-184

## Pipeline Stage Non-Conflict
- **Owns:** Batch construction with diversity penalty
- **Alternative to:** Single-point selectors (META-181..184 applied B times)
- **Coexists with:** META-184 (density-weighted) — density feeds uncertainty; batch then enforces diversity

## Test Plan
- λ=0: verify batch = top-B by uncertainty (ties broken by index)
- λ large + all-identical sims: verify batch = B distinct highest-uncertainty points
- B=1: verify reduces to META-181 argmax
- B=|U|: verify returns permutation of full pool
- Negative λ or B=0: verify raises ValueError
