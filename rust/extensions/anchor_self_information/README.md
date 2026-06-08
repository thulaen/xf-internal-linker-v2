# anchor_self_information

Shannon byte-bigram entropy hot-path kernel, ported from C++ to Rust and
exposed to Python as `extensions.anchor_self_information` via
[PyO3](https://pyo3.rs) + [maturin](https://www.maturin.rs).

The kernel exposes one function, `bigram_entropy(text) -> float`, which returns
the Shannon entropy `H(X) = -SUM p(x) log2(p(x))` (in bits) of the distribution
of adjacent byte pairs (bigrams) in `text`. It counts the UTF-8 *bytes* of the
input — exactly like the C++ kernel it replaces — so non-ASCII anchors keep the
same entropy the running system already persisted as corpus statistics. The
entropy feeds an Iglewicz-Hoaglin (1993) modified z-score anomaly detector in
`apps/pipeline/services/anchor_garbage_signals.py`. Source: Shannon, C. E.
(1948), "A Mathematical Theory of Communication", Section 9.

The crate ships as `anchor_self_information.so` (the `cdylib`) and is imported
from Python as `extensions.anchor_self_information`. The plain-Rust core
(`bigram_entropy_bytes`) is also exposed as an `rlib` so `cargo test` and the
Criterion benchmark can exercise it without crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
