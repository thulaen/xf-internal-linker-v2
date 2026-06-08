# xf_kernels

Scaffold Rust kernel crate exposed to Python via [PyO3](https://pyo3.rs) and
built with [maturin](https://www.maturin.rs). It proves the
Rust → PyO3 → maturin → Python build path end to end and ports no real C++
kernel yet.

It exposes two trivial, hand-verifiable functions so a Python test can assert
the native module imports and computes correctly:

- `version()` — the crate version string.
- `l2_norm(values)` — the Euclidean (L2) norm of a list of floats.

The compute core (`l2_norm_core`) is plain Rust over a slice, so `cargo test`
exercises it directly without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
