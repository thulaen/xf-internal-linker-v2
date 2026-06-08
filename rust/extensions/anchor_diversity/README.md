# anchor_diversity

FR-045 anchor-diversity / exact-match reuse guard hot-path kernel, ported from
C++ to Rust and exposed to Python as `extensions.anchor_diversity` via
[PyO3](https://pyo3.rs) + the [`numpy`](https://docs.rs/numpy) crate +
[maturin](https://www.maturin.rs).

`evaluate_batch(active_anchor_counts, exact_match_counts_before,
min_history_count, max_exact_match_share, max_exact_match_count,
hard_cap_enabled)` is the batched arithmetic inner loop of the FR-045 scorer.
It takes two parallel read-only int32 numpy arrays plus four scalar settings and
returns a dict of eight parallel numpy arrays (`projected_exact_count`,
`projected_exact_share`, `share_overflow`, `count_overflow_norm`, `spam_risk`,
`score_anchor_diversity`, `state_index`, `would_block`). Python owns the anchor
normalization, the neutral-case short-circuits, and the `round(..., 6)`
diagnostics composition; this kernel only does the straight-line f64 arithmetic.

All math is deterministic IEEE-754 double-precision (`+ - * / max min`), so the
kernel reproduces the C++ artifact and the pure-Python oracle
(`anchor_diversity.py::_arithmetic_via_python`) to within the `1e-6` parity floor
the acceptance test (`backend/tests/test_parity_anchor_diversity.py`) enforces.

State-index encoding: `1=neutral_no_history`, `2=neutral_below_threshold`,
`3=penalized_exact_share`, `4=penalized_exact_count`, `5=blocked_exact_count`
(states `0=disabled` and `6=neutral_no_anchor` are handled by the Python caller).

The crate ships as `anchor_diversity.so` (the `cdylib`) and is imported from
Python as `extensions.anchor_diversity`. The plain-Rust core
(`evaluate_anchor_diversity_core`) is also exposed as an `rlib` so `cargo test`
and the Criterion benchmark can exercise it without crossing the Python
boundary.

Part of the Python → Rust hot-path migration. See
`docs/PYTHON-RUST-MIGRATION-PLAN.md` and `RUST-FIRST.md`. FR-045 sources: Google
Search Central internal-linking best-practices and patent US20110238644A1.
