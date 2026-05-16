# lesson-index — fast in-process index supporting Rules A-F

**Status:** Draft (2026-05-15) — implements the Day-1 scaffold from the approved
plan at `~/.claude/plans/you-will-finish-every-cryptic-sphinx.md`.

## What this is

A single C++ Pybind11 extension (`extensions.lesson_index`) hosting three
independent sub-indices that share a 512 MB RAM cap. The extension is the
fast path under the new ABSOLUTE rules:

- **Rule A — 20× speedup gate.** `PerfBaselineCache` stores per-function timing
  baselines so `verify_perf_speedup` and `check-perf-proof.py` can compute
  speedups in sub-microsecond time without re-running benchmarks.
- **Rule B — Strict Red-Green-Refactor TDD.** `read_scoped_lessons` (which calls
  into `ScopedLessonIndex`) surfaces prior Red-phase discoveries for the
  touched area, so future cycles pre-check known traps.
- **Rule C — Spec citations.** `CitationCache` stores resolved metadata (title,
  authors, year, accessibility) keyed by canonical reference (DOI / patent
  number / RFC number / stable URL). The hook validates citations in
  sub-millisecond.
- **Rule D — Scoped lesson reading.** Same as Rule B: ART-keyed by repo path.
- **Rule E — Test-artefact cleanup.** The `lesson_pattern` category lookup hits
  `ScopedLessonIndex`.
- **Rule F — Universal hook plain-English failures.** This extension is itself
  benchmarked and TDD'd; its hooks must emit plain-English failures.

## Sources of truth

| Sub-index | Algorithm | Source |
|---|---|---|
| `ScopedLessonIndex` | Adaptive Radix Tree (ART) | Leis, V., Kemper, A., & Neumann, T. (2013). "The Adaptive Radix Tree: ARTful Indexing for Main-Memory Databases." *IEEE 29th International Conference on Data Engineering (ICDE)*, 38–49. DOI: 10.1109/ICDE.2013.6544812 |
| `PerfBaselineCache` | Cuckoo hashing | Pagh, R., & Rodler, F. F. (2001). "Cuckoo Hashing." *Algorithms — ESA 2001*, LNCS 2161, 121–133. DOI: 10.1007/3-540-44676-1_10 |
| `CitationCache` | Robin Hood hashing | Celis, P., Larson, P.-Å., & Munro, J. I. (1985). "Robin Hood Hashing." *26th Annual Symposium on Foundations of Computer Science (FOCS)*, 281–288. DOI: 10.1109/SFCS.1985.48 |
| Memory accounting | jemalloc-style introspection | Evans, J. (2006). "A Scalable Concurrent malloc(3) Implementation for FreeBSD." *BSDcan*. — used as the reference for `mallinfo2`-style RSS accounting. |
| Snapshot integrity | CRC-32C checksum | RFC 3309 — "Stream Control Transmission Protocol (SCTP) Checksum Change." Specifies the CRC-32C polynomial (Castagnoli) and the canonical table-driven implementation. |

`[SPEC CITED: feature=lesson-index kind=doi id=10.1109/ICDE.2013.6544812 verified_at=2026-05-15T20:55:00Z]`
`[SPEC CITED: feature=lesson-index kind=doi id=10.1007/3-540-44676-1_10 verified_at=2026-05-15T20:55:00Z]`
`[SPEC CITED: feature=lesson-index kind=doi id=10.1109/SFCS.1985.48 verified_at=2026-05-15T20:55:00Z]`
`[SPEC CITED: feature=lesson-index kind=rfc id=RFC3309 verified_at=2026-05-15T20:55:00Z]`

## Parameters

- ART node-type promotion: 4 → 16 → 48 → 256 (per Leis 2013 §4.1).
- Cuckoo table count: 2; max kick-out depth: 16; load factor target: 0.5.
- Robin Hood max probe distance: 64 slots; resize at load factor 0.7.
- Snapshot magic: `"XFLI"` (4 bytes); version: `1` (u32); checksum: CRC-32C
  over the entire payload AFTER the header.

## Memory budget at typical scale

| Sub-index | Per-entry | Target scale | At target |
|---|---|---|---|
| ScopedLessonIndex | ~150 B | 1 M lessons | ~150 MB |
| PerfBaselineCache | ~64 B | 50 K functions | ~3.2 MB |
| CitationCache | ~512 B | 10 K citations | ~5 MB |
| **Total typical** | — | — | **~168 MB** |
| **Hard cap** | — | — | **512 MB** |

## Lazy memory release

Default `idle_timeout_seconds = 300`. Each sub-index records `last_accessed_ns`
on every public method call. A background thread (started lazily on first
sub-index instantiation) checks every 30 seconds; if any sub-index has been
idle longer than its timeout, it calls `snapshot_and_free()`:

1. Acquire write lock.
2. Persist binary snapshot to `/app/data/lesson_index/{scoped|perf|citation}.bin`
   via tmp + atomic rename.
3. Clear in-memory data structures.
4. Release write lock.

Next public method call on the freed sub-index triggers a cold-load from the
snapshot (< 200 ms for 1 M ART entries).

Manual API: `idx.reclaim_now()` for operator-driven release. Memory pressure
trigger: if `xf::lesson_index::memory_bytes_total() > 0.9 * 512 MB`, the
oldest-idle sub-index is force-reclaimed.

## Concurrency

- Each sub-index uses `std::shared_mutex` for reader-many / writer-one.
- ART traversal uses an RCU-style read path: readers operate on a snapshot
  pointer; writers swap the pointer atomically.
- Cuckoo and Robin Hood tables use exclusive locks during `put`/`erase` and
  shared locks during `get`.

## Crash resilience

Every snapshot starts with:
```
offset 0:  4 bytes   "XFLI"                  // magic
offset 4:  4 bytes   uint32_t version=1
offset 8:  8 bytes   uint64_t payload_size
offset 16: 4 bytes   uint32_t crc32c_payload  // computed over [24, 24+payload_size)
offset 20: 4 bytes   uint32_t reserved=0
offset 24: payload_size bytes  // sub-index-specific binary
```

On load, if the magic or version mismatches, the loader throws
`std::runtime_error` with a plain-English message naming the path. If the
checksum mismatches, the loader treats the snapshot as corrupt and starts
empty (logged via `apps.ops_feed.emit`).

## Public API

See `backend/extensions/include/lesson_index.h` for the canonical C++
interface and `backend/extensions/lesson_index.cpp` for the Pybind11
binding. Python callers use:

```python
from extensions import lesson_index
scoped = lesson_index.ScopedLessonIndex()
perf = lesson_index.PerfBaselineCache()
cite = lesson_index.CitationCache()
```

## TDD discipline

This extension is implemented Red-Green-Refactor:
- Red: GTest cases in `backend/extensions/tests/test_lesson_index.cpp`
  must initially fail.
- Green: minimum implementation in `lesson_index.cpp` to make tests pass.
- Refactor: clang-format + clang-tidy + cppcheck + Mull mutation testing
  drive cleanup. Test code is held to the same standard as production.

## Performance targets

- `add` (ART): > 100 K ops/s at 1 M entries.
- `find_by_path` (ART): p99 < 5 µs at 1 M entries.
- `get` (Cuckoo): p99 < 1 µs at 50 K entries.
- `get` (Robin Hood): p99 < 2 µs at 10 K entries.
- Cold start from snapshot (1 M ART): < 1 s.
- Memory at typical scale: < 200 MB.

A Google Benchmark suite under `backend/extensions/benchmarks/bench_lesson_index.cpp`
asserts these via `--benchmark_min_time=0.3s`. Failing perf targets blocks
the commit through `.githooks/check-perf-proof.py`.
