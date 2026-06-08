# linkparse

BBCode / HTML / bare-URL link parser hot-path kernel, ported from C++ to Rust
and exposed to Python as `extensions.linkparse` via [PyO3](https://pyo3.rs) +
[maturin](https://www.maturin.rs).

`find_urls(raw_bbcode: str) -> list[tuple[str, str, str, int, int]]` scans a raw
forum/HTML string in three deterministic passes — BBCode `[url=...]...[/url]`
anchors, HTML `<a href="...">...</a>` anchors, and bare `http(s)://` URLs — with
a span-overlap suppression rule (BBCode wins over HTML wins over bare) and a
final stable sort by `(start, end, extraction_method)`. Each tuple is
`(url, anchor_text, extraction_method, start, end)` where `extraction_method` is
one of `bbcode_anchor`, `html_anchor`, `bare_url` and `start`/`end` are byte
offsets into the input.

The parser is a pure deterministic byte-string state machine — no floating
point, no hashing — so it reproduces the C++ kernel byte-for-byte. The
in-service Python reference (`link_parser.py::_find_urls_py`) and the 15-case
parity test pin the contract.

The crate ships as `linkparse.so` (the `cdylib`) and is imported from Python as
`extensions.linkparse`. The plain-Rust core (`find_urls_core`) is also exposed
as an `rlib` so `cargo test` and the Criterion benchmark can exercise it without
crossing the Python boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`.
