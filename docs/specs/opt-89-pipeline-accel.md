# OPT-89 -- Pipeline Scoring Orchestrator

## Overview
**Category:** Pipeline orchestration
**Extension file:** `pipeline_accel.cpp` (NEW)
**Expected speedup:** >=3x over Python dispatch loop (eliminates 6K+ GIL cycles per run)
**RAM:** <5 MB | **Disk:** <1 MB
**Research basis:** Standard function-call overhead elimination via batched dispatch. Reduces Python/C++ boundary crossings from O(destinations * stages) to O(1).

## Algorithm

Single C++ entry point that, for one destination, calls the existing C-exported functions from other extensions in sequence: (1) simsearch cscore_and_topk for semantic candidates, (2) inv_index search for keyword candidates, (3) fieldrel score_field_tokens, (4) rareterm evaluate_rare_terms, (5) phrasematch longest_contiguous_overlap, (6) scoring cscore_full_batch for composite. One GIL release covers all 6 stages. Data stays in C++ memory between stages -- no Python round-trip.

## C++ Interface (pybind11)

```cpp
// pipeline_accel.cpp
// py::dict score_destination_batch(
//     py::array_t<float> dest_embeddings,
//     py::array_t<float> sentence_embeddings,
//     py::dict config);
//
// Returns dict of {destination_id: scored_candidates}.
// Python fallback: ranker.py score_destination_matches()
```

## Memory Budget
- Runtime RAM: <5 MB (reuses existing extension memory)
- Disk: <1 MB

## Performance Target
- Target: >=3x faster than Python dispatch loop
- Benchmark: 1K destinations x 6 stages = 6K avoided GIL cycles

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
- Links against existing C-exported functions from simsearch, scoring, inv_index, fieldrel, rareterm, phrasematch
- Must be built AFTER those extensions

## Test Plan
- Output matches Python ranker.py score_destination_matches() within 1e-4 for all scores
- Edge cases: zero candidates, single destination, missing embedding
