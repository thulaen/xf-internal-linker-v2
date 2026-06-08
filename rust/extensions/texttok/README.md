# texttok

ASCII word tokenizer hot-path kernel, ported from C++ to Rust and exposed to
Python as `extensions.texttok` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs).

The crate ships as `texttok.so` (the `cdylib`) and is imported from Python as
`extensions.texttok`. The plain-Rust core (`tokenize_text_batch_core`) is also
exposed as an `rlib` so `cargo test` and the Criterion benchmark can exercise
it without crossing the Python boundary.

It exposes one module-level function:

```python
tokenize_text_batch(texts: list[str], stopwords: Iterable[str]) -> list[frozenset[str]]
```

Each input text is split on every non-`[0-9A-Za-z]` byte boundary, each token is
ASCII-lowercased, one optional apostrophe-joined run is folded in (the
contraction rule, e.g. `don't`), empty tokens and stopwords are dropped, and the
surviving unique tokens are returned as a Python `frozenset`. The outer list
order matches the input order. Scanning is byte-level (not Unicode codepoints),
matching the C++ kernel and the Python regex reference
(`TOKEN_RE = [A-Za-z0-9]+(?:'[A-Za-z0-9]+)?`) exactly.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
