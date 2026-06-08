# anchor_descriptiveness

Anchor-text descriptiveness hot-path kernel, ported from C++ to Rust and exposed
to Python as `extensions.anchor_descriptiveness` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs).

Two free functions:

- `damerau_levenshtein(a: str, b: str) -> int` — Damerau-Levenshtein edit
  distance with adjacent transposition (Damerau 1964, CACM 7(3):171-176),
  `O(n*m)` time and `O(min(n,m))` memory via three rolling rows.
- `char_trigram_jaccard(a: str, b: str) -> float` — Jaccard resemblance over the
  set of 3-byte character n-grams of the whitespace-collapsed inputs
  (Broder 1997).

Both operate on UTF-8 **bytes** to reproduce the replaced C++ kernel
byte-for-byte. The pure-Python reference
(`anchor_garbage_signals.py::_damerau_levenshtein_py` /
`_char_trigram_jaccard_py`) is the cross-language parity oracle.

The crate ships as `anchor_descriptiveness.so` (the `cdylib`) and is imported
from Python as `extensions.anchor_descriptiveness`. The plain-Rust cores
(`damerau_levenshtein_core`, `char_trigram_jaccard_core`) are also exposed as an
`rlib` so `cargo test` and the Criterion benchmark can exercise them without
crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
