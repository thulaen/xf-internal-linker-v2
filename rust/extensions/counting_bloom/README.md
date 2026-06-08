# counting_bloom

Counting Bloom filter hot-path kernel, ported from C++ to Rust and exposed to
Python as `extensions.counting_bloom` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs). A counting Bloom filter (Fan, Cao, Almeida &
Broder 2000, "Summary Cache") is a fixed-size table of small counters that
answers approximate set membership and, unlike a plain Bloom filter, supports
deletion: `add` increments counters, `remove` decrements them, and `contains`
reports membership with no false negatives (false positives are expected).

The crate ships as `counting_bloom.so` (the `cdylib`) and is imported from
Python as `extensions.counting_bloom`. The plain-Rust core (`CountingBloomCore`)
is also exposed as an `rlib` so `cargo test` and the Criterion benchmark can
exercise it without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
