# passagesim

FR-053 passage-level MaxSim kernel, ported from C++ to Rust and exposed to
Python as `extensions.passagesim` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs).

The crate ships as `passagesim.so` (the `cdylib`) and is imported from Python
as `extensions.passagesim`. The plain-Rust core (`max_sim_slice`) is also
exposed as an `rlib` so `cargo test` and the Criterion benchmark can exercise
it without crossing the Python boundary.

`maxsim(query, matrix)` returns `(best_sim, best_idx)` — the maximum dot
product between the query and any single passage row, plus the 0-based index
of that row (the ColBERT MaxSim aggregation). Ties keep the lowest row index;
an empty matrix returns `(0.0, 0)` and never raises.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
