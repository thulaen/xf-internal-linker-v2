# CPP-FIRST.md — C++ Is The Default Compute Path

**Status:** PARAMOUNT. Every AI agent reads this before adding a new hot-path function or modifying an existing one.

## The Rule

C++ extensions are the first-choice compute path for any function that runs more than once per ranker call, per-candidate scoring loop, or per-document import. Python remains the fallback and the reference implementation only.

If a hot path is currently Python-only, the next session that touches it must either:
1. Port it to a C++ extension following the pattern in [`backend/extensions/`](backend/extensions/), OR
2. File a Report Registry entry explaining why the C++ port is impossible (e.g. requires a Python-only library at the boundary) AND prove via benchmark that the Python path runs under 5 ms per call.

## What Counts As A "Hot Path"

- Any function called inside `score_destination_matches` per candidate
- Any function called inside the candidate-retrieval Stage 1 per host
- Any function in the Celery embedding loop
- Any function in `text_cleaner.py` regex chain (called per imported post)
- Any cosine / Euclidean / Jaccard / KL / JSD / similarity computation
- Any sort / partial-sort / heap operation over more than 100 items
- Any sketch (MinHash / Bloom / HyperLogLog / Count-Min) build or query

## What Does NOT Count

- Settings reads (Postgres latency dominates)
- Dashboard aggregates (called once per page render)
- Celery task orchestration (one call per beat tick)
- Migration data backfills (one-shot, not on hot path)
- Model loading (cached after first import)

## Pattern To Follow

Look at [`backend/extensions/passagesim.cpp`](backend/extensions/passagesim.cpp) as the canonical example. The shape is:

1. **Plain C function** (`extern "C"`) that takes raw `float*` / `uint8_t*` / `size_t` arguments. Lives at the top of the `.cpp`. Wrapped in `extern "C"` so it can be benchmarked from a non-pybind11 binary.
2. **Header** at [`backend/extensions/include/<name>_core.h`](backend/extensions/include/) declaring the C function so the bench binary can link against it. The pybind11 wrapper does NOT need to live in the header.
3. **pybind11 wrapper** at the bottom, gated by `#ifndef XF_BENCH_MODE` so the bench compile picks up the C function without the Python glue.
4. **Google Test** at [`backend/extensions/tests/test_<name>.cpp`](backend/extensions/tests/) — three or more parity tests against a hand-computed expected value.
5. **Google Benchmark** at [`backend/extensions/benchmarks/bench_<name>.cpp`](backend/extensions/benchmarks/) — three input sizes per the Mandatory Benchmark Rule.
6. **Setup.py registration** at [`backend/extensions/setup.py`](backend/extensions/setup.py) with the right compile flags (`-O3 -march=native` Linux / `/O2 /arch:AVX2` Windows).
7. **CMake registration** in both [`backend/extensions/CMakeLists.txt`](backend/extensions/CMakeLists.txt) (tests) and [`backend/extensions/benchmarks/CMakeLists.txt`](backend/extensions/benchmarks/CMakeLists.txt) (benches).
8. **Python fallback** in the consuming service. The pattern is `try: from extensions import X; HAS_X = True; except ImportError: HAS_X = False`. The fallback is the reference Python implementation, never a third-party shim.
9. **Diagnostic surfacing.** The consumer logs a one-time warning on import failure AND adds an `ErrorLog` row via `ingest_error()` so the System Health page shows the C++ vs Python state.

## Performance Floors (From CPP-RULES.md §25)

| Kernel class | Required speedup vs Python ref |
|---|---|
| Mission-critical hot path (passagesim, scoring) | ≥10× |
| Standard hot path (quantemb, ivf_index, pagerank) | ≥3× |
| Build-time / offline (codebook training) | ≥2× |

If your benchmark misses the floor, file a Report Registry entry and ask before merging.

## Diagnostic Visibility

Every hot path that has a C++ kernel surfaces its activation status on `/diagnostics` via the `native_scoring` ServiceStatusSnapshot:

- `runtime_path`: `cpp` (live) | `python` (fallback active)
- `fallback_active`: bool
- `fallback_reason`: short string
- `benchmark_status`: `green` (within floor) | `yellow` (off floor) | `red` (regressed >2×)

If the operator sees `runtime_path: python` for a kernel they expect to be C++, the import either failed or the .so is missing — a `make build-ext` rebuild fixes it.

## Forbidden Patterns

- ❌ Adding a hot-path function without a C++ kernel ("we'll port it later" never happens)
- ❌ Importing a third-party Python library on the hot path when the algorithm is < 100 lines
- ❌ Replacing a working C++ kernel with a numpy/scipy call to "simplify"
- ❌ Falling back to Python AND claiming the C++ path is "live" without an `ErrorLog` warning
- ❌ Adding a `.cpp` file with no Google Test or no Google Benchmark (CPP-RULES §16 violation)

## Forward-Thinking Note

The user has an i5-12450H today and may upgrade to a workstation-class CPU later. The C++ extensions are compiled with `-march=native` so they automatically pick up AVX-512 / VNNI / AMX instructions on the new chip without code changes. The Python fallback would not. Every hot path in C++ is one less perf cliff on the upgrade.
