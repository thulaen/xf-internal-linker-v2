//! FR-011 field-aware relevance hot-path kernel, ported from the C++
//! `fieldrel` kernel (`backend/extensions/fieldrel.cpp`) to Rust and exposed to
//! Python as the native module `extensions.fieldrel` via `PyO3`.
//!
//! The single function `score_field_tokens` scores how well one document field
//! matches a set of query tokens using a BM25F-style fielded extension of BM25
//! (Robertson, Zaragoza & Taylor 2004, "Simple BM25 extension to multiple
//! weighted fields", CIKM 2004, doi:10.1145/1031171.1031181). For each token it
//! computes an IDF-like presence weight, a BM25 term-frequency normalization
//! with field-length normalization, and a host-term-frequency cap of `2.0`;
//! keeps the top-`max_matched` tokens by a deterministic total order; averages
//! the kept scores; and squashes the mean to `[0, 1)` via `x / (1 + x)`.
//!
//! ## Parity basis (port note)
//!
//! Parity is EXACT. A production caller
//! (`backend/apps/pipeline/services/field_aware_relevance.py`) feeds the result
//! into the FR-011 ranking signal, and an existing parity test asserts the
//! kernel score equals the Python reference for representative profiles. The
//! math is fully deterministic `f64` (no hashing, no float32, no SIMD, no RNG)
//! with a total-order sort, so exact agreement is both achievable and required.
//! This port keeps the same `f64` arithmetic and the same total order
//! (`token_score` desc → `field_tf` desc → token asc) as the C++ kernel.

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

/// One token's score plus the two secondary sort keys, mirroring the C++
/// `ScoredToken` struct.
struct ScoredToken {
    token: String,
    field_tf: i32,
    token_score: f64,
}

/// Plain-Rust BM25F field scorer (no `PyO3`). Returns the field score in
/// `[0, 1)`, or an error message when the count lists are not all the same
/// length as `tokens`.
///
/// All intermediate arithmetic is `f64`, matching the C++ kernel bit-for-bit.
///
/// # Errors
///
/// Returns `Err` when `host_tfs`, `field_tfs`, or `field_presence_counts` has a
/// length different from `tokens` — the four lists must be positionally
/// aligned. The wrapper maps this to a Python `RuntimeError`.
#[allow(clippy::too_many_arguments)]
pub fn score_field_tokens_core(
    tokens: &[String],
    host_tfs: &[i32],
    field_tfs: &[i32],
    field_presence_counts: &[i32],
    field_length: i32,
    reference_length: f64,
    b_value: f64,
    field_count: i32,
    bm25_k1: f64,
    max_matched: i32,
) -> Result<f64, &'static str> {
    let token_count = tokens.len();
    if host_tfs.len() != token_count
        || field_tfs.len() != token_count
        || field_presence_counts.len() != token_count
    {
        return Err("All token lists must be positionally aligned and the same length");
    }
    if token_count == 0 || max_matched <= 0 {
        return Ok(0.0);
    }

    let mut scored: Vec<ScoredToken> = Vec::with_capacity(token_count);
    for index in 0..token_count {
        let idf = ((1.0 + f64::from(field_count))
            / (1.0 + f64::from(field_presence_counts[index])))
        .ln_1p();
        let denominator = f64::from(field_tfs[index])
            + bm25_k1
                * (1.0 - b_value + b_value * (f64::from(field_length) / reference_length.max(1.0)));
        let tf_norm = if denominator > 0.0 {
            (f64::from(field_tfs[index]) * (bm25_k1 + 1.0)) / denominator
        } else {
            0.0
        };
        let token_score = tf_norm * idf * 2.0_f64.min(f64::from(host_tfs[index]));
        scored.push(ScoredToken {
            token: tokens[index].clone(),
            field_tf: field_tfs[index],
            token_score,
        });
    }

    // Total order matching the C++ comparator: token_score descending, then
    // field_tf descending, then token ascending (lexicographic). `total_cmp`
    // gives a deterministic order even though inputs are finite, and keeps
    // clippy happy (no `partial_cmp().unwrap()`).
    scored.sort_by(|left, right| {
        right
            .token_score
            .total_cmp(&left.token_score)
            .then(right.field_tf.cmp(&left.field_tf))
            .then(left.token.cmp(&right.token))
    });

    // `max_matched > 0` is guaranteed by the early-return guard above, so the
    // conversion to usize never loses a sign; `unwrap_or(0)` is unreachable.
    let keep_count = usize::try_from(max_matched).unwrap_or(0).min(scored.len());
    let sum: f64 = scored[..keep_count].iter().map(|s| s.token_score).sum();
    // `keep_count <= token_count`, a small token count well under 2^52, so the
    // usize -> f64 conversion is exact in every realistic input.
    #[allow(clippy::cast_precision_loss)]
    let field_raw = sum / keep_count as f64;
    Ok(field_raw / (1.0 + field_raw))
}

/// `score_field_tokens(tokens, host_tfs, field_tfs, field_presence_counts,
/// field_length, reference_length, b_value, field_count, bm25_k1, max_matched)
/// -> float`.
///
/// Thin wrapper around [`score_field_tokens_core`] that maps the length-mismatch
/// error to a Python `RuntimeError`, preserving the C++ `std::runtime_error`
/// contract so callers catching `RuntimeError` keep working.
#[pyfunction]
// PyO3 extracts a Python `list` into an owned `Vec`, so these args are
// necessarily by-value at the boundary even though the core only borrows them.
#[allow(clippy::too_many_arguments, clippy::needless_pass_by_value)]
fn score_field_tokens(
    tokens: Vec<String>,
    host_tfs: Vec<i32>,
    field_tfs: Vec<i32>,
    field_presence_counts: Vec<i32>,
    field_length: i32,
    reference_length: f64,
    b_value: f64,
    field_count: i32,
    bm25_k1: f64,
    max_matched: i32,
) -> PyResult<f64> {
    score_field_tokens_core(
        &tokens,
        &host_tfs,
        &field_tfs,
        &field_presence_counts,
        field_length,
        reference_length,
        b_value,
        field_count,
        bm25_k1,
        max_matched,
    )
    .map_err(PyRuntimeError::new_err)
}

/// The Python module definition. The module name (`fieldrel`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact imports as
/// `extensions.fieldrel`. Registering `score_field_tokens` keeps the health
/// probe's expected attribute present.
#[pymodule]
fn fieldrel(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(score_field_tokens, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::score_field_tokens_core;

    /// Pure-Python reference re-implemented in Rust for the parity assertions:
    /// the exact formulas from `field_aware_relevance.py` and `fieldrel.cpp`.
    /// Used only to cross-check the core against an independent computation.
    #[allow(clippy::too_many_arguments)]
    fn reference(
        tokens: &[&str],
        host_tfs: &[i32],
        field_tfs: &[i32],
        presence: &[i32],
        field_length: i32,
        reference_length: f64,
        b_value: f64,
        field_count: i32,
        bm25_k1: f64,
        max_matched: i32,
    ) -> f64 {
        let mut scores: Vec<(f64, i32, String)> = Vec::new();
        for i in 0..tokens.len() {
            let idf = ((1.0 + f64::from(field_count)) / (1.0 + f64::from(presence[i]))).ln_1p();
            let denom = f64::from(field_tfs[i])
                + bm25_k1
                    * (1.0 - b_value
                        + b_value * (f64::from(field_length) / reference_length.max(1.0)));
            let tf_norm = if denom > 0.0 {
                (f64::from(field_tfs[i]) * (bm25_k1 + 1.0)) / denom
            } else {
                0.0
            };
            let ts = tf_norm * idf * 2.0_f64.min(f64::from(host_tfs[i]));
            scores.push((ts, field_tfs[i], tokens[i].to_owned()));
        }
        scores.sort_by(|a, b| b.0.total_cmp(&a.0).then(b.1.cmp(&a.1)).then(a.2.cmp(&b.2)));
        let keep = usize::try_from(max_matched).unwrap_or(0).min(scores.len());
        #[allow(clippy::cast_precision_loss)]
        let raw: f64 = scores[..keep].iter().map(|s| s.0).sum::<f64>() / keep as f64;
        raw / (1.0 + raw)
    }

    fn owned(tokens: &[&str]) -> Vec<String> {
        tokens.iter().map(|t| (*t).to_owned()).collect()
    }

    #[test]
    fn length_mismatch_host_tfs_errors() {
        // host_tfs shorter than tokens -> RuntimeError-equivalent Err. Pins the
        // first clause of the length guard.
        let r = score_field_tokens_core(
            &owned(&["a", "b"]),
            &[1],
            &[1, 1],
            &[1, 1],
            10,
            10.0,
            0.5,
            6,
            1.2,
            5,
        );
        assert!(r.is_err());
    }

    #[test]
    fn length_mismatch_field_tfs_errors() {
        let r = score_field_tokens_core(
            &owned(&["a", "b"]),
            &[1, 1],
            &[1],
            &[1, 1],
            10,
            10.0,
            0.5,
            6,
            1.2,
            5,
        );
        assert!(r.is_err());
    }

    #[test]
    fn length_mismatch_presence_errors() {
        let r = score_field_tokens_core(
            &owned(&["a", "b"]),
            &[1, 1],
            &[1, 1],
            &[1],
            10,
            10.0,
            0.5,
            6,
            1.2,
            5,
        );
        assert!(r.is_err());
    }

    #[test]
    fn empty_tokens_returns_zero() {
        let r = score_field_tokens_core(&[], &[], &[], &[], 10, 10.0, 0.5, 6, 1.2, 5);
        assert!(r.unwrap().abs() < 1e-12);
    }

    #[test]
    fn max_matched_zero_returns_zero() {
        // Boundary on the `max_matched <= 0` guard: 0 returns 0.0 even with
        // real tokens. Kills a `<= -> <` mutant.
        let r = score_field_tokens_core(&owned(&["a"]), &[1], &[1], &[1], 10, 10.0, 0.5, 6, 1.2, 0);
        assert!(r.unwrap().abs() < 1e-12);
    }

    #[test]
    fn max_matched_negative_returns_zero() {
        let r =
            score_field_tokens_core(&owned(&["a"]), &[1], &[1], &[1], 10, 10.0, 0.5, 6, 1.2, -3);
        assert!(r.unwrap().abs() < 1e-12);
    }

    #[test]
    fn result_in_unit_interval() {
        let r = score_field_tokens_core(
            &owned(&["alpha", "beta", "gamma"]),
            &[3, 1, 5],
            &[4, 2, 1],
            &[1, 3, 2],
            20,
            18.0,
            0.5,
            6,
            1.2,
            5,
        )
        .unwrap();
        assert!((0.0..1.0).contains(&r), "score {r} not in [0,1)");
    }

    #[test]
    fn matches_reference_keep_all() {
        // max_matched >= n keeps all tokens.
        let tokens = ["alpha", "beta", "gamma"];
        let host = [3, 1, 5];
        let field = [4, 2, 1];
        let pres = [1, 3, 2];
        let got = score_field_tokens_core(
            &owned(&tokens),
            &host,
            &field,
            &pres,
            20,
            18.0,
            0.5,
            6,
            1.2,
            5,
        )
        .unwrap();
        let want = reference(&tokens, &host, &field, &pres, 20, 18.0, 0.5, 6, 1.2, 5);
        assert!((got - want).abs() < 1e-12, "got {got} want {want}");
    }

    #[test]
    fn matches_reference_truncated_top_k() {
        // max_matched < n truncates to the top-k after sorting.
        let tokens = ["alpha", "beta", "gamma", "delta", "eps"];
        let host = [3, 1, 5, 2, 4];
        let field = [4, 2, 1, 6, 3];
        let pres = [1, 3, 2, 5, 1];
        let got = score_field_tokens_core(
            &owned(&tokens),
            &host,
            &field,
            &pres,
            30,
            22.0,
            0.75,
            6,
            1.2,
            2,
        )
        .unwrap();
        let want = reference(&tokens, &host, &field, &pres, 30, 22.0, 0.75, 6, 1.2, 2);
        assert!((got - want).abs() < 1e-12, "got {got} want {want}");
    }

    #[test]
    fn host_tf_is_capped_at_two() {
        // A token with host_tf 100 must score the same as host_tf 2 (cap), all
        // else equal. Build two single-token fields differing only in host_tf.
        let high =
            score_field_tokens_core(&owned(&["x"]), &[100], &[3], &[1], 10, 10.0, 0.5, 6, 1.2, 5)
                .unwrap();
        let cap =
            score_field_tokens_core(&owned(&["x"]), &[2], &[3], &[1], 10, 10.0, 0.5, 6, 1.2, 5)
                .unwrap();
        assert!((high - cap).abs() < 1e-12, "host_tf cap not applied");
    }

    #[test]
    fn tie_break_field_tf_then_token() {
        // Two tokens with identical token_score but different field_tf must be
        // ordered field_tf-desc; with max_matched=1 the kept one is the higher
        // field_tf. We can't easily force identical token_score with different
        // field_tf via the formula, so instead assert determinism: the same
        // inputs always give the same result regardless of input order.
        let a = score_field_tokens_core(
            &owned(&["a", "b", "c"]),
            &[2, 2, 2],
            &[1, 1, 1],
            &[2, 2, 2],
            10,
            10.0,
            0.5,
            6,
            1.2,
            2,
        )
        .unwrap();
        let b = score_field_tokens_core(
            &owned(&["c", "b", "a"]),
            &[2, 2, 2],
            &[1, 1, 1],
            &[2, 2, 2],
            10,
            10.0,
            0.5,
            6,
            1.2,
            2,
        )
        .unwrap();
        assert!((a - b).abs() < 1e-12, "result depends on input order");
    }
}
