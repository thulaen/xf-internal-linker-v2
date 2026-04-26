# OPT-90 -- Pixie Weighted Random Walk

## Overview
**Category:** Python pybind11 native extension -- graph
**Extension file:** `backend/extensions/pixie_walk.cpp` (NEW) + pybind11 module bindings
**Expected speedup:** >=3x over a single-threaded NumPy-based PixieWalk reference path
**RAM:** <5 MB | **Disk:** <1 MB
**Research basis:** Eksombatchai C. et al., "Pixie: A System for Recommending 3+ Billion Items to 200+ Million Users in Real-Time", Pinterest, WWW 2018. Walker alias method for O(1) weighted sampling (Walker, 1977).

> **Provenance note (2026-04-26):** This spec was originally written for the C# HttpWorker era when hot-path C++ extensions were called from C# via P/Invoke (`ScoringInterop.cs`). After the 2026-04 C# decommission, all hot-path extensions are pybind11 modules called directly from Python. The mathematical content and benchmarks are unchanged.

## Algorithm

Build CSR adjacency with edge weights from the graph. For each query node, perform N random walks of length L. At each step, select next node via Walker alias method (O(1) per sample vs O(degree) for linear scan). Accumulate visit counts. TBB parallel_for over walks with thread-local xoshiro256** PRNG. Return top-K visited nodes by count.

## C++ Interface (pybind11)

```cpp
// pixie_walk.cpp — exported as a pybind11 module function
// PYBIND11_MODULE(pixie_walk, m) {
//     m.def("walk",
//         [](py::array_t<uint32_t> indptr, py::array_t<uint32_t> indices,
//            py::array_t<float> weights, uint32_t num_nodes, uint32_t query_node,
//            uint32_t num_walks, uint32_t walk_length, uint32_t top_k)
//         -> py::tuple { /* returns (node_ids, scores) */ });
// }
//
// Python caller imports `pixie_walk` and gets back numpy arrays directly.
```

## Memory Budget
- Runtime RAM: <5 MB (CSR graph + alias tables)
- Disk: <1 MB

## Performance Target
- Target: >=3x faster than a single-threaded NumPy-based PixieWalk Python reference
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
- pybind11 binding registered in `backend/extensions/setup.py`

## Test Plan
- Visit distribution matches the Python reference within statistical tolerance (chi-squared, p>0.01) — see `backend/tests/test_parity_pixie_walk.py`
- Edge cases: isolated node, fully connected graph, self-loops, zero-weight edges
