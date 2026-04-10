# OPT-85 -- BBCode Text Cleaner

## Overview
**Category:** Text processing
**Extension file:** `bbcclean.cpp` (NEW)
**Expected speedup:** >=3x over Python regex-based clean_bbcode()
**RAM:** <2 MB | **Disk:** <1 MB
**Research basis:** Standard finite-state-machine text processing (Aho & Ullman, Compilers 1986). Single-pass state machine avoids regex backtracking.

## Algorithm

Single-pass finite state machine. States: NORMAL, IN_TAG, IN_QUOTE_BLOCK, IN_CODE_BLOCK. Scans raw_text character-by-character, tracks nesting depth for QUOTE/CODE blocks (case-insensitive match on [QUOTE and [CODE). Strips all BBCode tags ([TAG]...[/TAG]) and collapses whitespace. No regex engine. O(n) time, O(1) extra space.

## C++ Interface (pybind11)

```cpp
// bbcclean.cpp
// std::string clean_bbcode(const std::string& raw_text);
// std::vector<std::string> clean_bbcode_batch(
//     const std::vector<std::string>& texts);
//
// Python fallback: text_cleaner.py clean_bbcode()
```

## Memory Budget
- Runtime RAM: <2 MB (processes one string at a time, output buffer reused)
- Disk: <1 MB

## Performance Target
- Target: >=3x faster than Python regex-based clean_bbcode()
- Benchmark: 100K posts x 10KB average, batch mode

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
- Output matches Python clean_bbcode() exactly
- Edge cases: empty string, no BBCode, nested QUOTE inside QUOTE (3 deep), unclosed tags, mixed case [QuOtE], very long post (1MB)
