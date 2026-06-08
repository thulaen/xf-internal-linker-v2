# generic_anchor_matcher

Aho-Corasick generic-anchor matcher hot-path kernel, ported from C++ to Rust
and exposed to Python as `extensions.generic_anchor_matcher` via
[PyO3](https://pyo3.rs) + [maturin](https://www.maturin.rs). An Aho-Corasick
automaton (Aho & Corasick 1975, "Efficient String Matching: An Aid to
Bibliographic Search", Communications of the ACM 18(6):333-340) matches a list
of generic-anchor phrases against an input string in a single linear pass and
returns the distinct phrases that occur as substrings.

The crate ships as `generic_anchor_matcher.so` (the `cdylib`) and is imported
from Python as `extensions.generic_anchor_matcher`. The plain-Rust core
(`AutomatonCore`) is also exposed as an `rlib` so `cargo test` and the Criterion
benchmark can exercise it without crossing the Python boundary. Matching is over
raw UTF-8 bytes (case- and unicode-byte-exact), reproducing the former C++
kernel byte-for-byte.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
