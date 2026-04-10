# OPT-90 -- Pixie Weighted Random Walk

## Overview
**Category:** C# native interop -- graph
**Extension file:** `pixie_walk.cpp` (NEW) + C# P/Invoke in `ScoringInterop.cs`
**Expected speedup:** >=3x over C# single-threaded LINQ-based PixieWalk()
**RAM:** <5 MB | **Disk:** <1 MB
**Research basis:** Eksombatchai C. et al., "Pixie: A System for Recommending 3+ Billion Items to 200+ Million Users in Real-Time", Pinterest, WWW 2018. Walker alias method for O(1) weighted sampling (Walker, 1977).

## Algorithm

Build CSR adjacency with edge weights from the graph. For each query node, perform N random walks of length L. At each step, select next node via Walker alias method (O(1) per sample vs O(degree) for linear scan). Accumulate visit counts. TBB parallel_for over walks with thread-local xoshiro256** PRNG. Return top-K visited nodes by count.

## C++ Interface (exported as C function for P/Invoke)

```cpp
// pixie_walk.cpp
// extern "C" int32_t cpixie_walk(
//     const uint32_t* indptr, const uint32_t* indices, const float* weights,
//     uint32_t num_nodes, uint32_t query_node,
//     uint32_t num_walks, uint32_t walk_length, uint32_t top_k,
//     uint32_t* out_node_ids, float* out_scores);
//
// C# P/Invoke signature in ScoringInterop.cs.
```

## Memory Budget
- Runtime RAM: <5 MB (CSR graph + alias tables)
- Disk: <1 MB

## Performance Target
- Target: >=3x faster than C# single-threaded LINQ-based PixieWalk()
- Benchmark: 2K walks x 10 steps x 50K nodes

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
- C# calls via P/Invoke following existing ScoringInterop.cs pattern

## Test Plan
- Visit distribution matches C# reference within statistical tolerance (chi-squared, p>0.01)
- Edge cases: isolated node, fully connected graph, self-loops, zero-weight edges
