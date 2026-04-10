# OPT-73 -- Abseil flat_hash_map for inv_index

## Overview
**Category:** Google library -- hash container
**Extension file:** `inv_index.cpp` (modify existing)
**Expected speedup:** >=3x hash lookups over `std::unordered_map`
**RAM:** Saves ~40% vs std (flat open-addressing layout) | **Disk:** ~5 MB shared Abseil install
**Research basis:** Kulukundis M., "Designing a Fast, Efficient, Cache-friendly Hash Table, Step by Step", CppCon 2017. Swiss Tables use SIMD probing with a flat, cache-friendly memory layout.

## Algorithm

Drop-in replace `std::unordered_map<uint32_t, std::vector<uint32_t>>` (posting lists) and `std::unordered_map<uint32_t, float>` (doc lengths) with `absl::flat_hash_map`. Swiss Tables use SSE2/SSSE3 metadata bytes for parallel slot probing. Open-addressing eliminates per-bucket linked lists. Average lookup: O(1) with fewer cache misses.

## C++ Interface (pybind11)

```cpp
// No API change -- drop-in type alias:
// using PostingMap = absl::flat_hash_map<uint32_t, std::vector<uint32_t>>;
// using DocLenMap = absl::flat_hash_map<uint32_t, float>;
// Existing add_document() and search() signatures unchanged.
```

## Memory Budget
- Runtime RAM: Net negative (saves ~40% hash overhead vs std::unordered_map)
- Disk: ~5 MB shared across all Abseil-using extensions

## Performance Target
- Target: >=3x faster than std::unordered_map for BM25 search()
- Benchmark: 10K documents, 500K unique tokens, 1000 query iterations

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
- Abseil C++ (absl, Apache 2.0) -- shared with OPT-74 through OPT-79
- Must compile with `-fno-exceptions -fno-rtti` (Abseil supports ABSL_NO_EXCEPTIONS mode)

## Test Plan
- Correctness: output matches Python reference within 1e-4
- Edge cases: empty index, single document, zero-length query, duplicate tokens
- Memory: verify RSS is lower than std::unordered_map baseline on same dataset
