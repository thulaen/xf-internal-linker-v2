# pagerank

Weighted PageRank / personalized PageRank / HITS power-iteration hot-path
kernel, ported from C++ to Rust and exposed to Python as `extensions.pagerank`
via [PyO3](https://pyo3.rs) + [maturin](https://www.maturin.rs) and the `numpy`
crate.

Three module-level functions, each running ONE iteration step of a graph
power-iteration over a weighted CSR adjacency matrix (row = target, col =
source); the Python callers drive the convergence loop:

- `pagerank_step` — one weighted PageRank step (Page, Brin, Motwani & Winograd
  1999), returning `(next_ranks, delta)` where `next_ranks` is L1-renormalised
  to sum to 1.0 and `delta` is the L1 change.
- `personalized_pagerank_step` — the same with a personalization (teleport)
  vector (Haveliwala 2002, doi:10.1145/511446.511513); renormalises only when
  the total mass is positive.
- `hits_step` — one weighted Kleinberg HITS authority/hub step (Kleinberg 1999,
  doi:10.1145/324133.324140); returns `(next_authority, next_hub)` without
  normalising (the Python driver owns normalisation).

`damping` here is the teleport probability (textbook `1 - alpha`, the opposite
of networkx's `alpha`).

The crate ships as `pagerank.so` (the `cdylib`) and is imported from Python as
`extensions.pagerank`. The plain-Rust cores are also exposed as an `rlib` so
`cargo test` and the Criterion benchmark can exercise them without crossing the
Python boundary. All accumulation is plain sequential `f64 +=` to match the C++
summation order bit-for-bit.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
