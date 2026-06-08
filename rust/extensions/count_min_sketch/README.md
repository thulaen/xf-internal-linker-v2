# count_min_sketch

Count-Min Sketch hot-path kernel, ported from C++ to Rust and exposed to Python
as `extensions.count_min_sketch` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs). A Count-Min Sketch (Cormode &
Muthukrishnan 2005) is a small fixed-size table that estimates how many times
each item was seen in a stream; its estimate never undercounts the true count.

The crate ships as `count_min_sketch.so` (the `cdylib`) and is imported from
Python as `extensions.count_min_sketch`. The plain-Rust core
(`CountMinSketchCore`) is also exposed as an `rlib` so `cargo test` and the
Criterion benchmark can exercise it without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
