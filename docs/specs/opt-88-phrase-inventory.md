# OPT-88 -- Phrase Inventory Builder

## Overview
**Category:** NLP acceleration
**Extension file:** `phrase_inventory.cpp` (NEW)
**Expected speedup:** >=3x over Python list/dict-based _build_destination_phrase_inventory()
**RAM:** <2 MB | **Disk:** <1 MB
**Research basis:** Standard n-gram extraction with position weighting (Manning & Schutze, Foundations of Statistical NLP, 1999).

## Algorithm

Input: list of text segments (title, headings, body) with position weights. For each segment, extract all n-grams (1 to max_n tokens). Deduplicate across segments, keeping highest position weight. Sort by weight descending. Output: top-K phrases per destination. Uses flat_hash_map for dedup (pairs well with OPT-73 Abseil).

## C++ Interface (pybind11)

```cpp
// phrase_inventory.cpp
// py::list build_phrase_inventories_batch(
//     const std::vector<std::vector<std::string>>& segments,
//     const std::vector<std::vector<float>>& segment_weights,
//     uint32_t max_n,
//     uint32_t top_k);
//
// Returns list of (phrase_tokens, weight) per destination.
```

## Memory Budget
- Runtime RAM: <2 MB (processes one destination at a time)
- Disk: <1 MB

## Performance Target
- Target: >=3x faster than Python list/dict-based phrase inventory
- Benchmark: 1K destinations x 500 candidate phrases

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
- None (standalone, optionally uses Abseil flat_hash_map if OPT-73 is installed)

## Test Plan
- Output matches Python reference within 1e-4 for weights, exact for phrase tokens
- Edge cases: empty segments, single token, max_n=1, duplicate phrases across segments
