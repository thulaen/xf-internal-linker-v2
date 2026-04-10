# OPT-84 -- Google Benchmark Harness

## Overview
**Category:** Google library -- benchmark
**Extension file:** New `benchmarks/` directory with per-extension benchmark files
**Expected speedup:** Indirect -- enables systematic performance regression detection
**RAM:** Dev-only | **Disk:** ~2 MB
**Research basis:** Google Benchmark open-source project (Apache 2.0). Industry-standard C++ microbenchmarking framework used by Abseil, gRPC, and Protobuf.

## Algorithm

Google Benchmark provides `BENCHMARK()` macros that run code in a tight loop, measure wall time, CPU time, and throughput. Each existing C++ extension gets a companion benchmark file (e.g., `bench_simsearch.cpp`) that exercises the hot path with production-sized input. Benchmarks run as part of CI to detect performance regressions before merge.

## C++ Interface (pybind11)

```cpp
// Not a pybind11 extension -- standalone benchmark executables.
// Example: benchmarks/bench_simsearch.cpp
// static void BM_ScoreAndTopK(benchmark::State& state) {
//   auto [embs, query] = setup_test_data(state.range(0));
//   for (auto _ : state) {
//     score_and_topk(query, embs, /*top_k=*/50);
//   }
//   state.SetItemsProcessed(state.iterations() * state.range(0));
// }
// BENCHMARK(BM_ScoreAndTopK)->Range(256, 65536);
```

## Memory Budget
- Runtime RAM: Dev-only (not shipped in production Docker image)
- Disk: ~2 MB (google-benchmark library)

## Performance Target
- Target: All 13 existing extensions have benchmark coverage
- Benchmark: Each benchmark file exercises the hot path with 3 input sizes (small/medium/large)

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
- Google Benchmark (google/benchmark, Apache 2.0)
- Dev-only: not linked into production .pyd/.so files

## Test Plan
- All 13 extensions have benchmark files
- Benchmarks compile and run without errors
- CI integration: benchmark results saved as JSON for trend tracking
