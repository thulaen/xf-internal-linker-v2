# OPT-91 -- HTML Content Extractor + CETR

## Overview
**Category:** C# native interop -- HTML
**Extension file:** `dom_extract.cpp` (NEW) + C# P/Invoke
**Expected speedup:** >=3x over AngleSharp multi-pass DOM extraction
**RAM:** <10 MB | **Disk:** <3 MB
**Research basis:** Weninger T. et al., "CETR -- Content Extraction via Tag Ratios", WWW 2010. Single-pass HTML5 tokenization without full DOM construction.

## Algorithm

Single-pass HTML5 tokenizer (not a full DOM parser). Scans raw HTML byte-by-byte tracking: (1) tag depth and type, (2) text content per block, (3) tag-to-text ratio per block (CETR), (4) link density per block, (5) heading extraction (h1-h6). Blocks with text density above threshold and link density below threshold are content. Boilerplate (nav, footer, sidebar) filtered by tag semantics. Returns structured result: title, headings[], content_text, links[(url, anchor)], meta_description.

## C++ Interface (exported as C function for P/Invoke)

```cpp
// dom_extract.cpp
// extern "C" int32_t cdom_extract(
//     const char* html, uint32_t html_len,
//     char* out_json, uint32_t out_json_capacity,
//     uint32_t* out_json_len);
// Returns extraction result as JSON string.
//
// C# deserializes JSON result into ContentExtractionResult struct.
```

## Memory Budget
- Runtime RAM: <10 MB (one HTML page in memory + output buffer)
- Disk: <3 MB

## Performance Target
- Target: >=3x faster than AngleSharp multi-pass DOM extraction
- Benchmark: 1K HTML pages x 100KB average

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
- None (standalone single-pass tokenizer, no external HTML parser library)

## Test Plan
- Extracted text matches AngleSharp reference output within 95% F1 score
- Edge cases: empty HTML, malformed HTML, huge single-line minified HTML, pages with no content (all navigation), pages with deeply nested tables
