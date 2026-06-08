# l2norm

L2 normalization hot-path kernel, ported from C++ to Rust and exposed to
Python as `extensions.l2norm` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs).

The crate ships as `l2norm.so` (the `cdylib`) and is imported from Python as
`extensions.l2norm`. The plain-Rust core (`normalize_l2_batch_buffer`) is also
exposed as an `rlib` so `cargo test` and the Criterion benchmark can exercise
it without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
