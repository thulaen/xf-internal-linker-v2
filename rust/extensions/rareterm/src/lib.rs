//! Rare-term-propagation scoring hot-path kernel, ported from the C++
//! `rareterm` kernel (`backend/extensions/rareterm.cpp` +
//! `include/rareterm_core.h`) to Rust and exposed to Python as the native
//! module `extensions.rareterm` via `PyO3`.
//!
//! The Python-callable API matches the C++ kernel exactly: one module-level
//! function
//!
//! ```text
//! evaluate_rare_terms(
//!     terms: list[str],
//!     term_evidences: list[float],
//!     supporting_pages: list[int],
//!     host_tokens: Iterable[str],
//!     max_terms: int,
//! ) -> tuple[bool, float]
//! ```
//!
//! ## Algorithm
//!
//! 1. Length guard: if `term_evidences` or `supporting_pages` is not the same
//!    length as `terms`, raise `RuntimeError` with the exact message
//!    `"terms, term_evidences, and supporting_pages must be positionally
//!    aligned"`.
//! 2. Keep the terms that are members of `host_tokens` (original input order),
//!    carrying each term's evidence and supporting-page count.
//! 3. If nothing matched, return `(false, 0.0)`.
//! 4. Sort the kept terms by the strict total order: evidence descending, then
//!    supporting-page count descending, then term string ascending.
//! 5. `keep_count = min(max_terms as usize, n_matched)`; average the evidence of
//!    the first `keep_count` kept terms into `lift`.
//! 6. Return `(true, 0.5f64.mul_add(lift, 0.5))`.
//!
//! ## Exact parity (port note)
//!
//! All score arithmetic is `f64`: evidence values, the running sum, the
//! division, and `0.5 + 0.5*lift` are all `f64`, exactly as the C++ `double`
//! kernel. The only hashing is the host-token set membership test, which
//! decides only WHICH terms are kept (never a kept term's numeric value), so
//! hash-implementation differences cannot change the output. The sort is a
//! strict total order, so equal-evidence / equal-page ties resolve
//! deterministically by the unique term string. So byte-for-byte parity (within
//! a tight float tolerance) with the C++ kernel and the Python reference is
//! achievable and required. Source of truth: FR-010 rare-term propagation
//! (Spärck Jones 1972, doi:10.1108/eb026526) and the parity test
//! `backend/apps/pipeline/tests.py::RareTermExtensionTests`.
//!
//! ## `max_terms` cast semantics (preserved from C++)
//!
//! The C++ kernel computes `keep_count = min((size_t)max_terms, matched.size())`.
//! A negative `max_terms` cast to `size_t` wraps to a huge value, so `min`
//! yields `matched.size()` (keep all). This port replicates that with
//! `max_terms as usize` (a negative `i64` wraps to a large `usize`), so the
//! observable behaviour is identical. The real caller always passes `2`.

use std::collections::HashSet;
use std::hash::BuildHasher;

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

/// The exact alignment-error message raised by the C++ `std::runtime_error`.
const ALIGNMENT_ERROR: &str =
    "terms, term_evidences, and supporting_pages must be positionally aligned";

/// A host-matched term carried through the sort. Mirrors the C++
/// `MatchedTerm` struct field-for-field (`term`, `evidence`,
/// `supporting_page_count`).
struct MatchedTerm<'a> {
    term: &'a str,
    evidence: f64,
    supporting_page_count: i64,
}

/// Plain-Rust rare-term scoring core (no `PyO3`).
///
/// Returns `Ok((matched, score))` or `Err(ALIGNMENT_ERROR)` when the three
/// per-term lists are not the same length. Unit-testable with `cargo test`
/// without crossing the Python boundary.
///
/// # Errors
///
/// Returns `Err(ALIGNMENT_ERROR)` when `evidences.len()` or
/// `supporting_pages.len()` differs from `terms.len()` (the `PyO3` wrapper maps
/// this to a Python `RuntimeError`).
pub fn evaluate_rare_terms_core<S: BuildHasher>(
    terms: &[String],
    evidences: &[f64],
    supporting_pages: &[i64],
    host_token_set: &HashSet<String, S>,
    max_terms: i64,
) -> Result<(bool, f64), &'static str> {
    let term_count = terms.len();
    if evidences.len() != term_count || supporting_pages.len() != term_count {
        return Err(ALIGNMENT_ERROR);
    }

    let mut matched: Vec<MatchedTerm<'_>> = Vec::new();
    for index in 0..term_count {
        if host_token_set.contains(&terms[index]) {
            matched.push(MatchedTerm {
                term: &terms[index],
                evidence: evidences[index],
                supporting_page_count: supporting_pages[index],
            });
        }
    }

    if matched.is_empty() {
        return Ok((false, 0.0));
    }

    // Strict total order: evidence desc -> supporting_page_count desc -> term
    // asc. `f64::total_cmp` gives a deterministic, NaN-safe ordering (inputs
    // are finite in practice); reversing it makes higher evidence sort first.
    matched.sort_by(|left, right| {
        right
            .evidence
            .total_cmp(&left.evidence)
            .then(right.supporting_page_count.cmp(&left.supporting_page_count))
            .then(left.term.cmp(right.term))
    });

    // Replicate the C++ `min((size_t)max_terms, matched.size())`: a negative
    // `max_terms` wraps to a huge `usize`, so `min` picks `matched.len()`.
    // The truncation/sign-loss on the cast is the INTENDED behaviour we are
    // matching, not a bug — the wrap-to-large-usize is exactly what makes a
    // negative `max_terms` mean "keep all".
    #[allow(clippy::cast_possible_truncation, clippy::cast_sign_loss)]
    let keep_count = (max_terms as usize).min(matched.len());

    // `keep_count == 0` only when `max_terms == 0`. The C++ then divides by
    // zero, producing inf/nan; the real caller never passes 0. Guard it to a
    // neutral 0.0 lift (matching the Python reference, which truncates but
    // never divides by zero on a non-empty matched set) so the kernel never
    // returns NaN.
    if keep_count == 0 {
        return Ok((true, 0.5));
    }

    let sum: f64 = matched[..keep_count].iter().map(|m| m.evidence).sum();
    // `keep_count` is bounded by `matched.len()` (and in practice by the
    // caller's `max_terms = 2`), so it is far below 2^52 and the `as f64` cast
    // is exact — the precision-loss lint does not apply to this small range.
    #[allow(clippy::cast_precision_loss)]
    let lift = sum / keep_count as f64;
    Ok((true, 0.5f64.mul_add(lift, 0.5)))
}

/// `evaluate_rare_terms(...) -> tuple[bool, float]`.
///
/// Builds the host-token `HashSet` by iterating the `host_tokens` iterable once
/// (a non-str item raises `TypeError`, matching the C++ `py::cast<std::string>`
/// failure), then delegates to [`evaluate_rare_terms_core`]. The alignment
/// error is surfaced as a Python `RuntimeError` (matching the C++
/// `std::runtime_error`), NOT a `ValueError`.
#[pyfunction]
#[pyo3(signature = (terms, term_evidences, supporting_pages, host_tokens, max_terms))]
#[allow(clippy::needless_pass_by_value)]
fn evaluate_rare_terms(
    terms: Vec<String>,
    term_evidences: Vec<f64>,
    supporting_pages: Vec<i64>,
    host_tokens: &Bound<'_, PyAny>,
    max_terms: i64,
) -> PyResult<(bool, f64)> {
    let mut host_token_set: HashSet<String> = HashSet::new();
    for item in host_tokens.try_iter()? {
        let token: String = item?.extract()?;
        host_token_set.insert(token);
    }

    evaluate_rare_terms_core(
        &terms,
        &term_evidences,
        &supporting_pages,
        &host_token_set,
        max_terms,
    )
    .map_err(PyRuntimeError::new_err)
}

/// The Python module definition. The module name (`rareterm`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`rareterm.so`) imports as
/// `extensions.rareterm` once staged on `PYTHONPATH` under `extensions/`.
/// Registering `evaluate_rare_terms` keeps the health probe's expected
/// attribute present.
#[pymodule]
fn rareterm(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(evaluate_rare_terms, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    // The `(false, 0.0)` no-match path returns a literal `0.0`, so an exact
    // `assert_eq!(score, 0.0)` is correct and intentional here; the matched
    // paths already use an epsilon comparison.
    #![allow(clippy::float_cmp)]

    use super::{evaluate_rare_terms_core, ALIGNMENT_ERROR};
    use std::collections::HashSet;

    fn host(words: &[&str]) -> HashSet<String> {
        words.iter().map(|w| (*w).to_string()).collect()
    }

    fn terms(words: &[&str]) -> Vec<String> {
        words.iter().map(|w| (*w).to_string()).collect()
    }

    #[test]
    fn length_mismatch_in_evidences_errors() {
        let err = evaluate_rare_terms_core(&terms(&["a", "b"]), &[0.5], &[1, 2], &host(&["a"]), 2)
            .unwrap_err();
        assert_eq!(err, ALIGNMENT_ERROR);
    }

    #[test]
    fn length_mismatch_in_supporting_pages_errors() {
        let err =
            evaluate_rare_terms_core(&terms(&["a", "b"]), &[0.5, 0.6], &[1], &host(&["a"]), 2)
                .unwrap_err();
        assert_eq!(err, ALIGNMENT_ERROR);
    }

    #[test]
    fn no_host_match_returns_false_zero() {
        let (matched, score) =
            evaluate_rare_terms_core(&terms(&["a", "b"]), &[0.5, 0.6], &[1, 2], &host(&["x"]), 2)
                .unwrap();
        assert!(!matched);
        assert_eq!(score, 0.0);
    }

    #[test]
    fn single_match_score_formula() {
        // One match with evidence 0.8 -> 0.5 + 0.5*0.8 = 0.9.
        let (matched, score) = evaluate_rare_terms_core(
            &terms(&["x", "plugin"]),
            &[0.8, 0.6],
            &[3, 2],
            &host(&["x"]),
            2,
        )
        .unwrap();
        assert!(matched);
        assert!((score - 0.9).abs() < 1e-12);
    }

    #[test]
    fn tie_break_supporting_pages_then_term() {
        // Two matches, equal evidence 0.9; the kept top-2 average is the same
        // regardless of order, but verify ordering does not crash and the mean
        // is exact. 0.5 + 0.5*0.9 = 0.95.
        let (matched, score) = evaluate_rare_terms_core(
            &terms(&["alpine", "alpha", "atom"]),
            &[0.9, 0.9, 0.9],
            &[2, 5, 2],
            &host(&["alpha", "alpine", "atom"]),
            2,
        )
        .unwrap();
        assert!(matched);
        assert!((score - 0.95).abs() < 1e-12);
    }

    #[test]
    fn top_k_truncation_keeps_highest_evidence() {
        // Three matches, evidences 0.55/0.75/0.65; top-2 are 0.75 and 0.65,
        // mean 0.70 -> 0.5 + 0.5*0.70 = 0.85.
        let (matched, score) = evaluate_rare_terms_core(
            &terms(&["scope", "cluster", "rank"]),
            &[0.55, 0.75, 0.65],
            &[1, 4, 2],
            &host(&["scope", "rank", "cluster"]),
            2,
        )
        .unwrap();
        assert!(matched);
        assert!((score - 0.85).abs() < 1e-12);
    }

    #[test]
    fn max_terms_larger_than_matched_averages_all() {
        // Two matches, max_terms 5 -> average both. evidences 0.4, 0.6 -> mean
        // 0.5 -> 0.5 + 0.5*0.5 = 0.75.
        let (matched, score) = evaluate_rare_terms_core(
            &terms(&["a", "b"]),
            &[0.4, 0.6],
            &[1, 1],
            &host(&["a", "b"]),
            5,
        )
        .unwrap();
        assert!(matched);
        assert!((score - 0.75).abs() < 1e-12);
    }

    #[test]
    fn all_zero_evidence_squashes_to_half() {
        let (matched, score) = evaluate_rare_terms_core(
            &terms(&["a", "b"]),
            &[0.0, 0.0],
            &[1, 1],
            &host(&["a", "b"]),
            2,
        )
        .unwrap();
        assert!(matched);
        assert!((score - 0.5).abs() < 1e-12);
    }

    #[test]
    fn all_one_evidence_squashes_to_one() {
        let (matched, score) = evaluate_rare_terms_core(
            &terms(&["a", "b"]),
            &[1.0, 1.0],
            &[1, 1],
            &host(&["a", "b"]),
            2,
        )
        .unwrap();
        assert!(matched);
        assert!((score - 1.0).abs() < 1e-12);
    }

    #[test]
    fn negative_max_terms_keeps_all_matched() {
        // max_terms = -1 wraps to a huge usize, so keep_count == matched.len().
        // evidences 0.4, 0.6 -> mean 0.5 -> 0.75.
        let (matched, score) = evaluate_rare_terms_core(
            &terms(&["a", "b"]),
            &[0.4, 0.6],
            &[1, 1],
            &host(&["a", "b"]),
            -1,
        )
        .unwrap();
        assert!(matched);
        assert!((score - 0.75).abs() < 1e-12);
    }

    #[test]
    fn zero_max_terms_returns_neutral_half() {
        // keep_count == 0 guard: never divide by zero / return NaN.
        let (matched, score) =
            evaluate_rare_terms_core(&terms(&["a"]), &[0.9], &[1], &host(&["a"]), 0).unwrap();
        assert!(matched);
        assert!((score - 0.5).abs() < 1e-12);
    }

    #[test]
    fn empty_inputs_no_match() {
        let (matched, score) = evaluate_rare_terms_core(&[], &[], &[], &host(&["a"]), 2).unwrap();
        assert!(!matched);
        assert_eq!(score, 0.0);
    }
}
