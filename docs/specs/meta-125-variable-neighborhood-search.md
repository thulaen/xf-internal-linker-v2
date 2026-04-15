# META-125 — Variable Neighborhood Search (VNS)

## Overview
**Category:** Metaheuristic local-search with structured restarts
**Extension file:** `variable_neighborhood_search.cpp`
**Replaces/improves:** Single-neighborhood local search (escapes local optima via neighborhood change)
**Expected speedup:** ≥5x over Python reference loop
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

```
Input: initial x, neighborhood structures {N_1, N_2, ..., N_{k_max}}, local search LS
Output: best x*

x ← x_0
for iter = 1..n_iters:
    k ← 1
    while k ≤ k_max:
        # shake k-th neighborhood N_k, local search, if improved keep; else try N_{k+1}
        x' ← random_point_in(N_k(x))                # shake
        x'' ← LS(x')                                 # intensify
        if cost(x'') < cost(x):
            x ← x''
            k ← 1                                   # restart with smallest neighborhood
        else:
            k ← k + 1                               # grow neighborhood
return x
```

- **Time complexity:** O(n_iters × (shake + LS))
- **Space complexity:** O(|solution|)
- **Convergence:** Alternates diversification (shake) and intensification (LS); no monotonic guarantee

## Academic Source
Mladenović N., Hansen P. "Variable neighborhood search." *Computers & Operations Research* 24(11):1097–1100, 1997. DOI: 10.1016/S0305-0548(97)00031-2.

## C++ Interface (pybind11)

```cpp
// VNS with user-supplied neighborhoods and local search
std::vector<int> vns(
    const int* initial_x, int n_items,
    std::function<float(const int*)> cost_fn,
    std::function<void(int*, int, uint64_t)> shake,        // in-place perturb at level k
    std::function<void(int*)> local_search,
    int k_max, int n_iters, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <15 MB
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector` with `reserve(n_items)`

## Performance Target
- Python baseline: pure-python VNS
- Target: ≥5x faster
- Benchmark: n_iters=5k × k_max ∈ {3, 5, 10} × n_items ∈ {50, 500, 5000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on solution buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on cost.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`.

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all. k_max ≥ 1 required.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU. Seeded RNG.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_125.py` | Best cost within 3% of Python reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than Python reference |
| 5 | `pytest test_edges_meta_125.py` | k_max=1, empty LS, constant cost handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- Composable with META-123 tabu (as LS), META-124 GRASP (as LS)

## Pipeline Stage Non-Conflict
**Owns:** Structured diversification via nested neighborhoods.
**Alternative to:** META-123 tabu, META-124 GRASP (VNS emphasizes neighborhood structure).
**Coexists with:** Any local-search provider; VNS wraps them.

## Test Plan
- p-median: within 5% of optimum for n ≤ 200
- k_max=1: verify reduces to shake + LS repeatedly (random restart)
- k_max=10 on TSP: verify neighborhood escalation engages
- NaN cost: verify raises ValueError
