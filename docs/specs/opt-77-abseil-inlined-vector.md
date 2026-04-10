# OPT-77 -- Abseil InlinedVector

## Overview
**Category:** Google library -- small-buffer vector
**Extension file:** `texttok.cpp`, `phrasematch.cpp` (modify existing)
**Expected speedup:** >=3x for small token lists (eliminates heap allocation)
**RAM:** Net negative (small vectors stay on stack) | **Disk:** ~5 MB shared Abseil install
**Research basis:** Kulukundis M., CppCon 2017. absl::InlinedVector stores up to N elements inline (no heap) and spills to heap only when N is exceeded.

## Algorithm

Replace `std::vector<std::string>` with `absl::InlinedVector<std::string, 32>` for token lists in texttok (typical sentence has <32 tokens) and phrasematch left/right token sequences. Avoids malloc/free for the common case. Falls back to heap seamlessly when exceeded.

## C++ Interface (pybind11)

```cpp
// No API change -- internal type alias:
// using TokenVec = absl::InlinedVector<std::string, 32>;
// tokenize_text_batch() and longest_contiguous_overlap() signatures unchanged.
```

## Memory Budget
- Runtime RAM: Net negative (32 strings * ~32 bytes SSO = ~1KB inline per call, avoids heap metadata)
- Disk: ~5 MB shared

## Performance Target
- Target: >=3x fewer heap allocations for typical workloads
- Benchmark: 10K texts, measure malloc count via asan allocator hooks

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
- Abseil C++ (shared with OPT-73-76, 78-79)

## Test Plan
- Correctness: identical output to current std::vector implementation
- Edge cases: empty input, exactly 32 tokens (boundary), 33+ tokens (spill to heap)
