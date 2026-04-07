# META-04 — Coordinate Ascent Ranker

## Overview
**Category:** Weight optimizer
**Extension file:** `coord_ascent.cpp`
**Replaces/improves:** Grid search or manual weight tuning in `recommended_weights.py`
**Expected speedup:** ≥5x over Python scipy.optimize per-dimension search
**RAM:** <5 MB | **Disk:** <1 MB

## Algorithm

```
Input: weight vector w ∈ ℝ^d, evaluation function NDCG(w), step sizes
Output: optimized w* = argmax NDCG(w)

for epoch = 1..max_epochs:
    for k = 1..d:
        w_k* = golden_section_search(
            f = λ δ → NDCG(w + δ × e_k),
            interval = [w_k - step, w_k + step],
            tol = 1e-4
        )
        w_k ← w_k*
    if |NDCG(w_new) - NDCG(w_old)| < convergence_tol:
        break
```

- **Time complexity:** O(max_epochs × d × eval_cost × log(1/tol))
- **Space complexity:** O(d) for weight vector
- **Convergence:** Guaranteed to monotonically increase NDCG each epoch (coordinate-wise convexity not required — golden section finds local max per coordinate)

## C++ Interface (pybind11)

```cpp
// Optimize weights one coordinate at a time via golden section search
std::vector<float> coord_ascent(
    const float* initial_weights, int d,
    const float* scores_matrix, const int* relevance_labels,
    int n_queries, int max_candidates_per_query,
    int max_epochs, float step_size, float tol
);
```

## Memory Budget
- Runtime RAM: <5 MB (weight vector + score cache)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(d)`

## Performance Target
- Python baseline: `scipy.optimize.minimize_scalar` called d times per epoch
- Target: ≥5x faster (avoids Python function call overhead per evaluation)
- Benchmark: 50 epochs × 50 features × 1000 queries

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on hot arrays.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks. Double accumulator for reductions >100 elements.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_04.py` | Output matches Python reference within 1e-4 |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than Python reference |
| 5 | `pytest test_edges_meta_04.py` | Empty, single, NaN/Inf, n=10000 all pass |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (standalone optimizer)

## Test Plan
- 2D Rosenbrock: verify converges to (1,1) within 100 epochs
- Identity weights: verify no change when already optimal
- NaN weight input: verify raises ValueError
- Single-dimension: verify golden section finds correct optimum
