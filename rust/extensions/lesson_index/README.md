# lesson_index

Three-sub-index in-process cache hot-path kernel, ported from C++ to Rust and
exposed to Python as `extensions.lesson_index` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs).

Three caches back the paper-trail / lesson workflow:

- `ScopedLessonIndex` — a path-keyed store of resolved-AutoIssue lessons with a
  prefix-match `find_by_path` sorted by `(severity desc, resolved_at desc)`.
- `PerfBaselineCache` — a `fn_sig` → performance-baseline map.
- `CitationCache` — a minimal capacity-managed cache (the Python service keeps
  the actual citation data in a pure-Python dict, so only `size` /
  `memory_bytes` / `reclaim_now` / `clear` are exposed here).

Each cache supports a binary snapshot (`save` / `load`) with a 24-byte header
(magic + version + payload size + CRC-32C) written atomically (tmp + rename).
`load` raises `RuntimeError` on a missing file, magic/version mismatch, CRC
mismatch, or truncation. CRC-32C follows RFC 3309 (Castagnoli polynomial
`0x82F63B78`), and `crc32c("") == 0`.

The crate ships as `lesson_index.so` (the `cdylib`) and is imported from Python
as `extensions.lesson_index`. The plain-Rust cores are also exposed as an `rlib`
so `cargo test` and the Criterion benchmark can exercise them without crossing
the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
