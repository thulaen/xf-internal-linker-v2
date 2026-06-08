# quantemb

Optimised Product Quantisation (OPQ) encoder + trainer kernel, ported from C++
to Rust and exposed to Python as `extensions.quantemb` via
[PyO3](https://pyo3.rs) + [maturin](https://www.maturin.rs).

The crate ships as `quantemb.so` (the `cdylib`) and is imported from Python as
`extensions.quantemb`. The plain-Rust cores (`opq_encode_core`,
`opq_train_core`) are also exposed as an `rlib` so `cargo test` and the
Criterion benchmark can exercise the math without crossing the Python boundary.

Two free functions:

- `opq_encode(vectors, rotation, codebooks)` → `uint8` code matrix `(N, m)`.
- `opq_train(vectors, m, k, n_iter)` → `(rotation, codebooks)` (identity
  rotation + deterministic Lloyd k-means codebooks).

The float32 arithmetic mirrors the C++ serial accumulation order **bit-for-bit**
(the persisted codes and codebook bytes are a durable database contract), so
the cores accumulate in `f32` with the same loop order as the C++ and use plain
`+=` (no FMA / SIMD reduction reordering).

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
