# rareterm

Rare-term-propagation scoring hot-path kernel, ported from C++ to Rust and
exposed to Python as `extensions.rareterm` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs).

The crate ships as `rareterm.so` (the `cdylib`) and is imported from Python as
`extensions.rareterm`. The plain-Rust core (`evaluate_rare_terms_core`) is also
exposed as an `rlib` so `cargo test` and the Criterion benchmark can exercise it
without crossing the Python boundary.

It exposes one module-level function:

```python
evaluate_rare_terms(
    terms: list[str],
    term_evidences: list[float],
    supporting_pages: list[int],
    host_tokens: Iterable[str],
    max_terms: int,
) -> tuple[bool, float]
```

It keeps the terms present in the host-token set, orders them by `(evidence
desc, supporting-page-count desc, term asc)`, averages the evidence of the top
`max_terms` kept terms into a lift, and returns `(matched, 0.5 + 0.5*lift)`. When
no term matches the host set it returns `(False, 0.0)`. It raises `RuntimeError`
when `term_evidences` or `supporting_pages` is not the same length as `terms`.

Implements the FR-010 rare-term-propagation signal (Spärck Jones 1972, "A
statistical interpretation of term specificity and its application in
retrieval", doi:10.1108/eb026526). All score arithmetic is `f64`.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
