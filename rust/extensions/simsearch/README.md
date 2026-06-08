# simsearch

Bounded top-k dot-product sentence-search kernel, ported from C++ to Rust and
exposed to Python as `extensions.simsearch` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs).

The crate ships as `simsearch.so` (the `cdylib`) and is imported from Python as
`extensions.simsearch`. The plain-Rust core (`score_and_topk_core`) is also
exposed as an `rlib` so `cargo test` and the Criterion benchmark can exercise
it without crossing the Python boundary.

## API

`score_and_topk(destination, sentences, candidate_rows, top_k) -> (indices, scores)`

Given a 1-D float32 query embedding, a 2-D C-contiguous float32 sentence
matrix, a 1-D int32 array of candidate row indices, and an integer `top_k`,
returns the top-k candidates by raw dot product, sorted by score descending.

### Port contract notes

- **`indices` are positions in the `candidate_rows` list, NOT sentence row
  indices.** The production caller maps each position back to a sentence id via
  `candidate_ids[i]`.
- The score is a raw single-precision dot product over the first
  `min(dest_dim, sentence_dim)` elements — no normalization (embeddings are
  pre-normalized upstream).
- Candidate rows outside `[0, num_sentences)` are skipped, reducing the result
  length below `top_k`.
- Result length is `min(top_k, valid_candidate_count)`; `top_k == 0` or an empty
  candidate list yields two empty arrays.
- **Tie-break:** equal scores are ordered by candidate-list position ascending.
  The original C++ min-heap left ties implementation-defined; this port makes
  them deterministic. For distinct scores the set and order are identical to the
  C++ kernel. The parity basis is `contract` (scores agree with the NumPy
  reference within `rtol=1e-5 / atol=1e-6`), not byte-exact, because both the
  kernel and NumPy/BLAS use different float reduction orders.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
