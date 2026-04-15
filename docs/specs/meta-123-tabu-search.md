# META-123 — Tabu Search

## Overview
**Category:** Metaheuristic local search (memory-based)
**Extension file:** `tabu_search.cpp`
**Replaces/improves:** Vanilla hill-climbing that cycles on plateaus
**Expected speedup:** ≥5x over Python tabu loop
**RAM:** <15 MB | **Disk:** <1 MB

## Algorithm

```
Input: initial solution x_0, neighborhood N(x), cost c, tabu tenure T, aspiration
Output: best solution x*

x ← x_0;  x_best ← x_0
tabu_list ← empty deque of size T
for iter = 1..n_iters:
    # move to best neighbor NOT in tabu list; tabu list stores last T moves
    candidates ← N(x)
    best_move ← null
    for (x', move) in candidates:
        if move ∉ tabu_list or c(x') < c(x_best):    # aspiration override
            if best_move is null or c(x') < c(best):
                best_move ← move; best ← x'
    x ← x_best_neighbor
    push_back(tabu_list, best_move); if len(tabu_list) > T: pop_front
    if c(x) < c(x_best): x_best ← x
return x_best
```

- **Time complexity:** O(n_iters × |N| × move_eval_cost)
- **Space complexity:** O(T + solution_size)
- **Convergence:** Escapes local minima via tabu memory; aspiration ensures we can revisit on big improvement

## Academic Source
Glover F. "Future paths for integer programming and links to artificial intelligence." *Operations Research* 13(5):533–549, 1986. DOI: 10.1016/0305-0548(86)90048-1.

## C++ Interface (pybind11)

```cpp
// Tabu search over discrete move set
std::vector<int> tabu_search(
    const int* initial_solution, int n_items,
    std::function<float(const int*)> cost_fn,
    std::function<void(const int*, std::vector<std::pair<int,int>>&)> neighbor_moves,
    int tabu_tenure, int n_iters, uint64_t seed
);
```

## Memory Budget
- Runtime RAM: <15 MB (solution + tabu deque + neighbor list)
- Disk: <1 MB (compiled .so/.pyd only)
- Allocation: `std::vector`/`std::deque` with `reserve`

## Performance Target
- Python baseline: pure-python tabu loop
- Target: ≥5x faster
- Benchmark: n_iters=10k × n_items ∈ {50, 500, 5000}

## Pre-Implementation Safety Checklist

**Compiler flags:** `-std=c++17 -O3 -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion -Wsign-conversion -Wshadow -Wdouble-promotion -Wnull-dereference -Wformat=2 -Wimplicit-fallthrough`

**Threading:** No `std::recursive_mutex`. No `volatile`. No detached threads. All `condition_variable::wait()` uses predicate form. All atomics document memory ordering. Spinlocks use `_mm_pause()` with 1000-iteration fallback.

**Memory:** No raw `new`/`delete` in hot paths. No `alloca`/VLA. No `void*` delete. Arena/pool/RAII only. Bounds-checked in debug. `reserve()` before known-size fills. Tabu list bounded by T.

**Object lifetime:** Self-assignment safe. No dangling `string_view` members. No `[&]` capture beyond scope. No return ref to local.

**Type safety:** Explicit `static_cast` for narrowing with comment. No signed/unsigned mismatch. No strict aliasing violation. All switch cases handled.

**SIMD:** No mixed SSE/AVX without `_mm256_zeroupper()`. Unaligned loads default. Max 12 YMM. `alignas(64)` on solution buffer.

**Floating point:** Flush-to-zero on init. NaN/Inf entry checks on cost.

**Performance:** No `std::endl` loops. No `std::function` hot loops. No `dynamic_cast`. `return x;` not `return std::move(x);`. Use `std::deque` or ring buffer for tabu list (O(1) push/pop).

**Error handling:** Destructors `noexcept`. Catch `const&`. Basic exception guarantee. pybind11 catches all.

**Build:** No cyclic includes. Static/anonymous namespace internals. Extension frees own memory.

**Security:** No `system()`. No `printf(user_string)`. Scrub sensitive memory. No TOCTOU.

See `backend/extensions/CPP-RULES.md` for full policy.

## Pre-Merge Gates

| Gate | Tool | Pass criteria |
|---|---|---|
| 1 | `setup.py build_ext` | Zero warnings with `-Werror` |
| 2 | `pytest test_parity_meta_123.py` | Best cost within 2% of Python reference |
| 3 | `ASAN=1 build + pytest` | Zero AddressSanitizer/UBSan errors |
| 4 | `bench_extensions.py` | ≥3x faster than Python reference |
| 5 | `pytest test_edges_meta_123.py` | T=0, empty neighborhood, single item handled |
| 6 | `valgrind --leak-check=full` | Zero leaks, zero errors |
| 7 | `TSAN=1 build + pytest` | Zero races (if threaded) |
| 8 | Human reviewer | CPP-RULES.md compliance confirmed |

## Dependencies
- None (caller supplies neighborhood and cost)

## Pipeline Stage Non-Conflict
**Owns:** Memory-based discrete/combinatorial local search.
**Alternative to:** Hill-climbing, simulated annealing for combinatorial subset selection.
**Coexists with:** META-124 GRASP, META-125 VNS, META-126 ALNS — chosen by `optimizer.metaheuristic`.

## Test Plan
- Small TSP (n=20): best tour within 5% of optimum
- Knapsack 50 items: within 2% of DP optimum
- T=0 equivalent to hill-climbing: verify same result
- NaN cost: verify raises ValueError
