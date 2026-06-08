//! Longest-contiguous-overlap phrase-matching hot-path kernel, ported from the
//! C++ `phrasematch` kernel (`backend/extensions/phrasematch.cpp`) to Rust and
//! exposed to Python as the native module `extensions.phrasematch` via `PyO3`.
//!
//! The Python-callable API matches the C++ kernel exactly: one module-level
//! function
//!
//! ```text
//! longest_contiguous_overlap(left: list[str], right: list[str]) -> int
//! ```
//!
//! It returns the token-count length of the longest run of tokens that appears
//! contiguously and in identical order in BOTH lists, or `0` when there is no
//! shared run or either list is empty.
//!
//! ## Algorithm
//!
//! Brute-force longest common contiguous substring over two token sequences.
//! For every start index in `left` and every start index in `right`, extend a
//! match counter while the tokens line up by exact string equality and both
//! indices stay in bounds; track the maximum match length. Time
//! `O(n * m * min(n, m))`; inputs are tiny in practice (token lists capped well
//! under ~30 tokens by the caller's phrase limits).
//!
//! ## Exact parity (port note)
//!
//! This is fully deterministic integer / string-equality work: no float math,
//! no hashing, no locale, no platform-dependent state. So byte-for-byte parity
//! with the C++ kernel and the pure-Python fallback
//! (`phrase_matching.py::_longest_contiguous_overlap`) is fully achievable and
//! is the stated contract. Token comparison is exact `String` equality — no
//! case-folding, no Unicode normalization, no trimming. Source of truth:
//! FR-008 phrase-based matching (Patent US7536408B2), and the parity test
//! `backend/apps/pipeline/tests.py::PhraseMatchExtensionTests`.
//!
//! ## Index types (no signed casts)
//!
//! The C++ kernel used `int` for the match counter and `size_t` for indices.
//! Here the count and all indices are `usize`: the result is a token count that
//! is always non-negative and bounded by `min(left.len(), right.len())`, so an
//! unsigned type is the natural fit and removes every signed-to-unsigned cast.
//! `usize` imports into Python as a plain non-negative `int`.

use pyo3::prelude::*;

/// Plain-Rust longest-contiguous-overlap core (no `PyO3`).
///
/// Returns the length (token count) of the longest run of tokens appearing
/// contiguously and in identical order in both slices, comparing tokens by
/// exact equality. Returns `0` when either slice is empty or there is no shared
/// run. Generic over the element type's `PartialEq` so it works for `&str`,
/// `String`, etc., and is unit-testable with `cargo test` without crossing the
/// Python boundary.
#[must_use]
pub fn longest_contiguous_overlap_core<T: PartialEq>(left: &[T], right: &[T]) -> usize {
    let mut best = 0usize;
    for left_start in 0..left.len() {
        for right_start in 0..right.len() {
            let mut match_len = 0usize;
            while left_start + match_len < left.len()
                && right_start + match_len < right.len()
                && left[left_start + match_len] == right[right_start + match_len]
            {
                match_len += 1;
            }
            if match_len > best {
                best = match_len;
            }
        }
    }
    best
}

/// `longest_contiguous_overlap(left: list[str], right: list[str]) -> int`.
///
/// Thin `PyO3` wrapper over [`longest_contiguous_overlap_core`]. `PyO3`
/// extracts the two `list[str]` into `Vec<String>` (raising `TypeError` on a
/// non-list or non-str element, matching the C++ `pybind11` behaviour) and the
/// `usize` result imports back into Python as a non-negative `int`.
#[pyfunction]
#[pyo3(signature = (left, right))]
// `PyO3` extracts each `list[str]` into an owned `Vec<String>` at the boundary
// (a borrowed `&[String]` is not a valid extraction target), and the brute-force
// core borrows them read-only — so the by-value arguments are unavoidable here,
// not a needless copy.
#[allow(clippy::needless_pass_by_value)]
fn longest_contiguous_overlap(left: Vec<String>, right: Vec<String>) -> usize {
    longest_contiguous_overlap_core(&left, &right)
}

/// The Python module definition. The module name (`phrasematch`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`phrasematch.so`) imports
/// as `extensions.phrasematch` once staged on `PYTHONPATH` under `extensions/`.
/// Registering `longest_contiguous_overlap` keeps the health probe's expected
/// attribute present.
#[pymodule]
fn phrasematch(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(longest_contiguous_overlap, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::longest_contiguous_overlap_core;

    fn overlap(left: &[&str], right: &[&str]) -> usize {
        longest_contiguous_overlap_core(left, right)
    }

    // The 10 example cases pinned in the port spec and the existing parity test
    // (backend/apps/pipeline/tests.py::PhraseMatchExtensionTests).

    #[test]
    fn both_empty_is_zero() {
        assert_eq!(overlap(&[], &[]), 0);
    }

    #[test]
    fn left_empty_is_zero() {
        assert_eq!(overlap(&[], &["a"]), 0);
    }

    #[test]
    fn right_empty_is_zero() {
        assert_eq!(overlap(&["a"], &[]), 0);
    }

    #[test]
    fn identical_lists_full_length() {
        assert_eq!(overlap(&["a", "b", "c"], &["a", "b", "c"]), 3);
    }

    #[test]
    fn disjoint_lists_is_zero() {
        assert_eq!(overlap(&["a", "b"], &["x", "y"]), 0);
    }

    #[test]
    fn shared_prefix_run() {
        assert_eq!(overlap(&["a", "b", "c"], &["a", "b", "x"]), 2);
    }

    #[test]
    fn shared_mid_list_run() {
        assert_eq!(
            overlap(&["x", "a", "b", "c", "y"], &["q", "a", "b", "c", "r"]),
            3
        );
    }

    #[test]
    fn shared_suffix_run_offset() {
        assert_eq!(overlap(&["x", "y", "a", "b"], &["q", "a", "b"]), 2);
    }

    #[test]
    fn single_token_in_pair() {
        assert_eq!(overlap(&["solo"], &["solo", "pair"]), 1);
    }

    #[test]
    fn longest_of_multiple_runs() {
        // "internal","links" is a contiguous run of length 2; "guide" appears in
        // both but not adjacent to that run, so the answer is 2.
        assert_eq!(
            overlap(
                &["guide", "internal", "links"],
                &["internal", "links", "guide"]
            ),
            2
        );
    }

    // Mutation-killing boundary tests beyond the example set.

    #[test]
    fn result_bounded_by_shorter_list() {
        // result <= min(len(left), len(right)).
        let out = overlap(&["a", "b", "c", "d"], &["a", "b"]);
        assert_eq!(out, 2);
        assert!(out <= 2);
    }

    #[test]
    fn repeated_tokens_pick_longest_run() {
        // Repeats must not double-count: "a","a","a" vs "a","a" -> 2, not 3.
        assert_eq!(overlap(&["a", "a", "a"], &["a", "a"]), 2);
    }

    #[test]
    fn single_token_match() {
        assert_eq!(overlap(&["x"], &["x"]), 1);
    }

    #[test]
    fn single_token_mismatch() {
        assert_eq!(overlap(&["x"], &["y"]), 0);
    }

    #[test]
    fn exact_string_equality_no_casefold() {
        // Token comparison is exact: "Internal" != "internal".
        assert_eq!(overlap(&["Internal"], &["internal"]), 0);
    }

    #[test]
    fn best_run_after_a_shorter_earlier_run() {
        // An earlier length-1 match must not mask a later length-3 match.
        assert_eq!(
            overlap(&["a", "x", "p", "q", "r"], &["a", "y", "p", "q", "r"]),
            3
        );
    }
}
