# OPT-74 -- Abseil flat_hash_set for texttok

## Overview
**Category:** Google library -- hash container
**Extension file:** `texttok.cpp` (modify existing)
**Expected speedup:** >=3x stopword membership test over `std::unordered_set`
**RAM:** Saves ~40% vs std | **Disk:** ~5 MB shared Abseil install
**Research basis:** Kulukundis M., "Designing a Fast, Efficient, Cache-friendly Hash Table, Step by Step", CppCon 2017.

## Algorithm

Drop-in replace `std::unordered_set<std::string>` (stopword set) with `absl::flat_hash_set<std::string>`. Swiss Tables SIMD probing eliminates hash collision chains. Stopword membership test is the inner-loop hot path called per token per text in batch.

## C++ Interface (pybind11)

```cpp
// No API change -- type alias only:
// using StopwordSet = absl::flat_hash_set<std::string>;
// tokenize_text_batch() signature unchanged.
```

## Memory Budget
- Runtime RAM: Net negative (flat layout, no per-bucket linked list nodes)
- Disk: ~5 MB shared

## Performance Target
- Target: >=3x faster tokenization throughput
- Benchmark: 10K texts, 200 stopwords, batch tokenization

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
- Abseil C++ (shared with OPT-73, 75-79)

## Test Plan
- Correctness: tokenized output matches Python reference exactly (frozenset equality)
- Edge cases: empty text, text with only stopwords, non-ASCII input, very long text
