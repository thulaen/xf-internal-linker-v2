# scoring (Rust kernel)

Composite ranking-score hot-path kernel, ported from the C++ `scoring` kernel
(`backend/extensions/scoring.cpp`) to Rust and exposed to Python as
`extensions.scoring` via PyO3 + maturin.

`calculate_composite_scores_full_batch(component_scores, weights, silo_scores)`
computes, for each row `i` of a 2-D float32 component matrix,
`out[i] = silo_scores[i] + dot(component_scores[i, :], weights[:])`, returning a
1-D float32 array of length `num_rows`. This is the ranker's final composite
score: each row is one link candidate, the columns are per-signal component
scores, `weights` are per-signal blend weights, and `silo_scores` is an additive
per-row structural bonus.

Accumulation is single precision (`f32`, plain `+=`) so the result agrees with
the C++ kernel and the Python reference within `rtol=1e-5, atol=1e-5`. Source:
the linear scoring function in Liu, "Learning to Rank for Information Retrieval"
(Foundations and Trends in IR, 2009, doi:10.1561/1500000016) §1.3.
