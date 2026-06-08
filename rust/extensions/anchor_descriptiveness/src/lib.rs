//! Anchor-text descriptiveness hot-path kernel, ported from the C++
//! `anchor_descriptiveness` kernel (`backend/extensions/anchor_descriptiveness.cpp`)
//! to Rust and exposed to Python as the native module
//! `extensions.anchor_descriptiveness` via `PyO3`.
//!
//! Two module-level functions match the C++ kernel exactly:
//!
//! ```text
//! damerau_levenshtein(a: str, b: str) -> int
//! char_trigram_jaccard(a: str, b: str) -> float
//! ```
//!
//! ## Algorithms
//!
//! - **`damerau_levenshtein`**: optimal-substructure dynamic program with the
//!   adjacent-transposition extension (Damerau 1964, CACM 7(3):171-176),
//!   `O(n*m)` time and `O(min(n,m))` memory via three rolling rows. The shorter
//!   input is swapped into `b` so the rows are `min(n,m)+1` wide.
//! - **`char_trigram_jaccard`**: Jaccard resemblance (Broder 1997) over the SET
//!   of 3-byte character n-grams of the whitespace-collapsed inputs. Returns
//!   `inter / union` as an `f64`, or `0.0` when either gram set is empty.
//!
//! ## Byte parity (port note)
//!
//! The C++ kernel operates on `std::string` bytes (UTF-8 code units), not
//! Unicode scalar values. This Rust port also operates on **bytes**
//! (`str::as_bytes`) so the edit distance and the trigram windows are
//! byte-for-byte identical to the replaced C++ artifact. The pure-Python
//! reference slices by code point, so for multi-byte Unicode the Python and C++
//! paths already diverge; this port matches the C++ authority. Both functions
//! are deterministic with no hashing-dependent output and a single IEEE-754
//! `int/int` division, so exact parity is achievable and required. Source of
//! truth: `backend/extensions/anchor_descriptiveness.cpp` and its byte-for-byte
//! parity statement against `anchor_garbage_signals.py`.

use std::collections::HashSet;

use pyo3::prelude::*;

/// Character n-gram length (3 = trigram). Matches the C++ `char_ngram`.
const CHAR_NGRAM: usize = 3;

/// Plain-Rust Damerau-Levenshtein core over bytes (no `PyO3`).
///
/// Returns the edit distance with adjacent transposition. Unit-testable with
/// `cargo test` without crossing the Python boundary.
#[must_use]
pub fn damerau_levenshtein_core(a: &[u8], b: &[u8]) -> usize {
    if a.is_empty() {
        return b.len();
    }
    if b.is_empty() {
        return a.len();
    }
    // Swap so `a` is the longer input -> rows are `min(n,m)+1` wide.
    let (a, b) = if a.len() < b.len() { (b, a) } else { (a, b) };
    let n = a.len();
    let m = b.len();

    let mut prev_prev_row = vec![0usize; m + 1];
    let mut prev_row: Vec<usize> = (0..=m).collect();
    let mut curr_row = vec![0usize; m + 1];

    for i in 1..=n {
        curr_row[0] = i;
        for j in 1..=m {
            let cost = usize::from(a[i - 1] != b[j - 1]);
            let insertion = curr_row[j - 1] + 1;
            let deletion = prev_row[j] + 1;
            let substitution = prev_row[j - 1] + cost;
            let mut best = insertion.min(deletion).min(substitution);
            // Damerau transposition — only when the adjacent characters swap.
            if i > 1 && j > 1 && a[i - 1] == b[j - 2] && a[i - 2] == b[j - 1] {
                best = best.min(prev_prev_row[j - 2] + cost);
            }
            curr_row[j] = best;
        }
        // Rotate: prev_prev <- prev, prev <- curr (reuse the freed buffer).
        std::mem::swap(&mut prev_prev_row, &mut prev_row);
        std::mem::swap(&mut prev_row, &mut curr_row);
    }
    prev_row[m]
}

/// Collapse every run of ASCII whitespace bytes into a single space (`0x20`).
/// Matches the C++ `collapse_whitespace` and the Python `re.sub(r"\s+", " ")`
/// for ASCII whitespace.
fn collapse_whitespace(text: &[u8]) -> Vec<u8> {
    let mut out: Vec<u8> = Vec::with_capacity(text.len());
    let mut last_space = false;
    for &byte in text {
        let is_space = matches!(byte, b' ' | b'\t' | b'\n' | b'\r' | 0x0b | 0x0c);
        if is_space {
            if !last_space {
                out.push(b' ');
                last_space = true;
            }
        } else {
            out.push(byte);
            last_space = false;
        }
    }
    out
}

/// Build the SET of `n`-byte character n-grams of the whitespace-collapsed
/// input. A non-empty string shorter than `n` yields the single-element set
/// `{norm}`; an empty string yields the empty set.
fn char_ngrams(text: &[u8], n: usize) -> HashSet<Vec<u8>> {
    let norm = collapse_whitespace(text);
    let mut out: HashSet<Vec<u8>> = HashSet::new();
    if norm.len() < n {
        if !norm.is_empty() {
            out.insert(norm);
        }
        return out;
    }
    for window in norm.windows(n) {
        out.insert(window.to_vec());
    }
    out
}

/// Plain-Rust char-trigram Jaccard core over bytes (no `PyO3`).
///
/// Returns `|A ∩ B| / |A ∪ B|` over the 3-byte n-gram sets, or `0.0` when
/// either set (or the union) is empty.
#[must_use]
pub fn char_trigram_jaccard_core(a: &[u8], b: &[u8]) -> f64 {
    let grams_a = char_ngrams(a, CHAR_NGRAM);
    let grams_b = char_ngrams(b, CHAR_NGRAM);
    if grams_a.is_empty() || grams_b.is_empty() {
        return 0.0;
    }
    // Iterate the smaller set, counting membership in the larger.
    let (smaller, larger) = if grams_a.len() <= grams_b.len() {
        (&grams_a, &grams_b)
    } else {
        (&grams_b, &grams_a)
    };
    let inter = smaller.iter().filter(|gram| larger.contains(*gram)).count();
    let union = grams_a.len() + grams_b.len() - inter;
    if union == 0 {
        return 0.0;
    }
    // Cardinalities are small integers, far below 2^52, so `as f64` is exact.
    #[allow(clippy::cast_precision_loss)]
    let result = inter as f64 / union as f64;
    result
}

/// `damerau_levenshtein(a, b) -> int`. Thin `PyO3` wrapper over the byte core.
#[pyfunction]
#[pyo3(signature = (a, b))]
fn damerau_levenshtein(a: &str, b: &str) -> usize {
    damerau_levenshtein_core(a.as_bytes(), b.as_bytes())
}

/// `char_trigram_jaccard(a, b) -> float`. Thin `PyO3` wrapper over the byte core.
#[pyfunction]
#[pyo3(signature = (a, b))]
fn char_trigram_jaccard(a: &str, b: &str) -> f64 {
    char_trigram_jaccard_core(a.as_bytes(), b.as_bytes())
}

/// The Python module definition. The module name (`anchor_descriptiveness`)
/// MUST match the `[lib] name` in `Cargo.toml` so the built artifact
/// (`anchor_descriptiveness.so`) imports as `extensions.anchor_descriptiveness`
/// once staged on `PYTHONPATH` under `extensions/`. Registering both functions
/// keeps the health probe's expected `damerau_levenshtein` attribute present.
#[pymodule]
fn anchor_descriptiveness(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(damerau_levenshtein, m)?)?;
    m.add_function(wrap_pyfunction!(char_trigram_jaccard, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::float_cmp)]

    use super::{char_trigram_jaccard_core, damerau_levenshtein_core};

    fn dl(a: &str, b: &str) -> usize {
        damerau_levenshtein_core(a.as_bytes(), b.as_bytes())
    }

    fn jac(a: &str, b: &str) -> f64 {
        char_trigram_jaccard_core(a.as_bytes(), b.as_bytes())
    }

    #[test]
    fn identical_strings_have_zero_distance() {
        assert_eq!(dl("hello", "hello"), 0);
    }

    #[test]
    fn adjacent_transposition_costs_one() {
        assert_eq!(dl("ab", "ba"), 1);
    }

    #[test]
    fn empty_inputs_return_other_length() {
        assert_eq!(dl("", "abc"), 3);
        assert_eq!(dl("abc", ""), 3);
        assert_eq!(dl("", ""), 0);
    }

    #[test]
    fn single_substitution() {
        assert_eq!(dl("cat", "cot"), 1);
    }

    #[test]
    fn insertion_and_deletion() {
        assert_eq!(dl("cat", "cart"), 1);
        assert_eq!(dl("cart", "cat"), 1);
    }

    #[test]
    fn longer_swapped_to_shorter_is_symmetric() {
        // The distance must be symmetric regardless of arg order (the core
        // swaps the longer into `a`).
        assert_eq!(dl("kitten", "sitting"), dl("sitting", "kitten"));
        assert_eq!(dl("kitten", "sitting"), 3);
    }

    #[test]
    fn transposition_vs_two_substitutions() {
        // "abcd" -> "abdc" is one transposition (distance 1), not two subs.
        assert_eq!(dl("abcd", "abdc"), 1);
    }

    #[test]
    fn identical_jaccard_is_one() {
        assert_eq!(jac("hello world", "hello world"), 1.0);
    }

    #[test]
    fn disjoint_jaccard_is_zero() {
        assert_eq!(jac("abc", "xyz"), 0.0);
    }

    #[test]
    fn empty_input_jaccard_is_zero() {
        assert_eq!(jac("", "abc"), 0.0);
        assert_eq!(jac("abc", ""), 0.0);
    }

    #[test]
    fn sub_trigram_strings_use_whole_string_as_only_gram() {
        // "ab" (len 2 < 3) -> set {"ab"}; identical -> jaccard 1.0.
        assert_eq!(jac("ab", "ab"), 1.0);
        // "ab" vs "cd": disjoint single-gram sets -> 0.0.
        assert_eq!(jac("ab", "cd"), 0.0);
    }

    #[test]
    fn whitespace_collapse_makes_spacing_irrelevant() {
        // "a  b" and "a b" collapse to the same byte string -> jaccard 1.0.
        assert_eq!(jac("a  b", "a b"), 1.0);
        assert_eq!(jac("a\t\nb", "a b"), 1.0);
    }

    #[test]
    fn partial_overlap_jaccard_is_a_rational() {
        // "abcd" trigrams {abc, bcd}; "abce" trigrams {abc, bce}. Intersection
        // {abc} = 1, union {abc, bcd, bce} = 3 -> 1/3.
        let value = jac("abcd", "abce");
        assert!((value - 1.0 / 3.0).abs() < 1e-12);
    }

    #[test]
    fn byte_level_distance_for_multibyte_input() {
        // A 2-byte UTF-8 char ("é" = 0xC3 0xA9) vs ASCII "e": the byte-level
        // distance differs from a code-point-level one. Pin the byte semantics
        // (2 bytes vs 1 byte -> distance 2: substitute one, insert/delete one).
        assert_eq!(dl("é", "e"), 2);
    }
}
