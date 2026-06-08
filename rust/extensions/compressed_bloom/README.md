# compressed_bloom

Compressed Bloom filter hot-path kernel, ported from C++ to Rust and exposed to
Python as `extensions.compressed_bloom` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs). A Bloom filter (Bloom 1970, "Space/Time
Trade-offs in Hash Coding with Allowable Errors") is a fixed-size bit array that
answers approximate set membership: `add` sets one bit per hash function and
`contains` reports membership with no false negatives (false positives are
expected and bounded by the table load).

The crate ships as `compressed_bloom.so` (the `cdylib`) and is imported from
Python as `extensions.compressed_bloom`. The plain-Rust core
(`CompressedBloomFilterCore`) is also exposed as an `rlib` so `cargo test` and
the Criterion benchmark can exercise it without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
