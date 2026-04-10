# OPT-83 -- FarmHash Custom Hasher

## Overview
**Category:** Google library -- hash function
**Extension file:** New `farmhash_hasher.h` header, used by all hash-container extensions
**Expected speedup:** >=3x string hashing over std::hash<string>
**RAM:** 0 additional | **Disk:** <1 MB
**Research basis:** Pike G., "FarmHash: A Family of Hash Functions", Google 2014. FarmHash provides high-quality, fast hash functions optimized for x86-64 with hardware CRC32 acceleration.

## Algorithm

Custom hasher struct wrapping `util::Hash64()` from FarmHash. Used as the Hash template parameter for absl::flat_hash_map/set (OPT-73 to 76) and any future hash containers. FarmHash uses hardware CRC32C instructions when available, falling back to multiply-shift chains. Produces 64-bit hashes with excellent distribution.

## C++ Interface (pybind11)

```cpp
// New header: farmhash_hasher.h
// struct FarmHasher {
//   size_t operator()(const std::string& s) const noexcept {
//     return util::Hash64(s.data(), s.size());
//   }
//   size_t operator()(uint32_t x) const noexcept {
//     return util::Hash64(reinterpret_cast<const char*>(&x), sizeof(x));
//   }
// };
// Usage: absl::flat_hash_map<std::string, uint32_t, FarmHasher>
```

## Memory Budget
- Runtime RAM: 0 (stateless hash function)
- Disk: <1 MB (header + FarmHash source)

## Performance Target
- Target: >=3x faster string hashing for typical token lengths (5-20 chars)
- Benchmark: 10M hash calls on production token vocabulary

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
- FarmHash (google/farmhash, MIT license)
- Note: if Abseil's built-in hash is sufficient, FarmHash can be optional. Benchmark both.

## Test Plan
- Correctness: hash function produces consistent output for same input across runs
- Distribution: chi-squared test on 1M hashes to verify uniformity
- Collision rate: verify collision rate <= 1/2^32 on production vocabulary
