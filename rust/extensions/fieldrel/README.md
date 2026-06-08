# fieldrel

FR-011 field-aware relevance hot-path kernel, ported from C++ to Rust and
exposed to Python as `extensions.fieldrel` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs). It scores how well a document field matches
a set of query tokens using a BM25F-style fielded extension of BM25 (Robertson,
Zaragoza & Taylor 2004, "Simple BM25 extension to multiple weighted fields",
CIKM 2004, doi:10.1145/1031171.1031181).

The single function `score_field_tokens` takes positionally-aligned token lists
plus BM25 parameters, computes a per-token BM25F score with an IDF-like presence
weight and a host-term-frequency cap, keeps the top-k tokens by a deterministic
total order, averages the kept scores, and squashes the mean to `[0, 1)` via
`x / (1 + x)`.

The crate ships as `fieldrel.so` (the `cdylib`) and is imported from Python as
`extensions.fieldrel`. The plain-Rust core (`score_field_tokens_core`) is also
exposed as an `rlib` so `cargo test` and the Criterion benchmark can exercise it
without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
