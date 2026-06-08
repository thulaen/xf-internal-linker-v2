# phrasematch

Longest-contiguous-overlap phrase-matching hot-path kernel, ported from C++ to
Rust and exposed to Python as `extensions.phrasematch` via
[PyO3](https://pyo3.rs) + [maturin](https://www.maturin.rs).

The crate ships as `phrasematch.so` (the `cdylib`) and is imported from Python
as `extensions.phrasematch`. The plain-Rust core
(`longest_contiguous_overlap_core`) is also exposed as an `rlib` so `cargo test`
and the Criterion benchmark can exercise it without crossing the Python
boundary.

It exposes one module-level function:

```python
longest_contiguous_overlap(left: list[str], right: list[str]) -> int
```

It returns the token-count length of the longest run of tokens that appears
contiguously and in the same order in BOTH lists, or `0` when there is no shared
run or either list is empty. Tokens are compared by exact string equality (no
case-folding, no normalization, no hashing). Implements the longest-contiguous-
overlap heuristic from FR-008 (Patent US7536408B2, phrase-based indexing).

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
