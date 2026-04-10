# OPT-87 -- Link Graph Reconciler

## Overview
**Category:** Graph acceleration
**Extension file:** `link_reconcile.cpp` (NEW)
**Expected speedup:** >=3x over Python dict-based _sync_existing_links_py()
**RAM:** <10 MB | **Disk:** <1 MB
**Research basis:** Standard sorted-merge set-difference algorithm (Knuth, TAOCP Vol. 3, Section 5.2.4).

## Algorithm

Input: current_links (array of (source_id, target_id, edge_hash) sorted by source,target) and db_links (same format, from database). Single-pass merge: walk both arrays simultaneously. If current has entry not in db: added. If db has entry not in current: removed. If both have entry but hash differs: changed. O(n+m) time where n=current, m=db.

## C++ Interface (pybind11)

```cpp
// link_reconcile.cpp
// py::tuple reconcile_links(
//     py::array_t<uint64_t> current,
//     py::array_t<uint64_t> db_state);
//
// Returns (added, changed, removed) as three numpy arrays
// of (source_id, target_id) pairs.
```

## Memory Budget
- Runtime RAM: <10 MB for 1M links
- Disk: <1 MB

## Performance Target
- Target: >=3x faster than Python dict-based reconciliation
- Benchmark: 100K posts x 100 links = 10M entries

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
- None (standalone extension)

## Test Plan
- Output matches Python reference exactly
- Edge cases: empty current, empty db, identical sets (no changes), all added, all removed
