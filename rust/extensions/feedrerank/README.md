# feedrerank

FR-013 explore/exploit rerank + FR-015 Maximal Marginal Relevance (MMR)
diversity hot-path kernel, ported from C++ to Rust and exposed to Python as
`extensions.feedrerank` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs) and the `numpy` crate.

Two module-level functions:

- `calculate_rerank_factors_batch` — a per-candidate rerank factor combining a
  Bayesian exploit estimate (with a `1e-9` denominator guard so zero priors plus
  zero totals stays finite), a linear observation-confidence blend toward the
  neutral `0.5`, and a UCB1 exploration bonus, clamped to `[0.5, 2.0]`.
- `calculate_mmr_scores_batch` — MMR diversity scores (Carbonell & Goldstein
  1998, SIGIR; patent US20070294225A1): `lambda * relevance - (1 - lambda) *
  max_similarity`, where `max_similarity` is the largest dot product between a
  candidate embedding and any already-selected embedding.

The crate ships as `feedrerank.so` (the `cdylib`) and is imported from Python as
`extensions.feedrerank`. The plain-Rust cores (`rerank_factors_core`,
`mmr_scores_core`) are also exposed as an `rlib` so `cargo test` and the
Criterion benchmark can exercise them without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
