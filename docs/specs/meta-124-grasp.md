# META-124 — GRASP (Greedy Randomised Adaptive Search Procedure)

## Overview
**Category:** Metaheuristic combinatorial optimizer (multi-start)
**Extension file:** `grasp.cpp`
**Replaces/improves:** Pure greedy construction that gets stuck in local optima
**Expected speedup:** ≥5x over Python reference loop
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

```
Input: element universe U, incremental cost, local search LS, n_restarts R, α ∈ [0,1]
Output: best solution

x_best ← null
# greedy randomised construction (RCL) + local search; repeat with different random seeds
for r = 1..R:
    x ← empty
    while not complete(x):
        C ← candidate_costs(x)
        c_min, c_max ← min(C), max(C)
        threshold ← c_min + α · (c_max - c_min)
        RCL ← {e : c(e) ≤ threshold}               # restricted candidate list
        e ← uniform_random(RCL)
        x ← x ∪ {e}
    x ← LS(x)                                      # local search to local optimum
    if cost(x) < cost(x_best) or x_best = null:
        x_best ← x
return x_best
```

- **Time complexity:** O(R × (construction_cost + LS_cost))
- **Space complexity:** O(|solution|)
- **Convergence:** No monotonic guarantee; each restart is independent

## Academic Source
Feo T.A., Resende M.G.C. "Greedy Randomized Adaptive Search Procedures." *Journal of Global Optimization* 6(2):109–133, 1995. DOI: 10.1007/BF01096763.

## C++ Interface (pybind11)

```cpp
// GRASP with caller-supplied construction and local search
std::vector<int> grasp(
    int n_items,
    std::function<float(int, const std::vector<int>&)> incremental_cost,
    std::function<void(std::vector<int>&)> local_search,
    float alpha, int n_restarts, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <15 MB (solution + candidate list)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_items)`

## Performance Target
- Python baseline: pure-python GRASP
- Target: ≥5x faster
- Benchmark: R ∈ {10, 100, 1000} × n_items ∈ {50, 500, 5000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback. Restarts parallelizable with OpenMP.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on candidate cost array.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on costs. Double accumulator for cost sum.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. α outside [0,1] raises.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_124.py` | Best cost within 3% of Python reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than Python reference |
| 5 | `pytest test_edges_meta_124.py` | α=0 (pure greedy), α=1 (random), R=1 handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Often pairs with META-123 tabu search as local-search phase

## Pipeline Stage Non-Conflict
**Owns:** Diversified multi-start combinatorial search.
**Alternative to:** Single-run greedy + local search.
**Coexists with:** META-123 tabu, META-125 VNS — GRASP can wrap tabu/VNS as LS.

## Test Plan
- Set cover: within 5% of optimal on small instances
- α=0 (pure greedy): verify deterministic single restart
- α=1 (pure random): verify diversity across restarts
- NaN cost: verify raises ValueError
