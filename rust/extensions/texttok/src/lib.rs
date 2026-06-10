//! ASCII word tokenizer hot-path kernel, ported from the C++ `texttok` kernel
//! (`backend/extensions/texttok.cpp` + `include/texttok_core.h`) to Rust and
//! exposed to Python as the native module `extensions.texttok` via `PyO3`.
//!
//! The Python-callable API matches the C++ kernel exactly: one module-level
//! function
//!
//! ```text
//! tokenize_text_batch(texts: list[str], stopwords: Iterable[str]) -> list[frozenset[str]]
//! ```
//!
//! For each text the kernel splits on every non-`[0-9A-Za-z]` byte, ASCII-
//! lowercases each token, folds in exactly one optional apostrophe-joined run
//! (the contraction rule), drops empty tokens and any token in the stopword
//! set, and returns the surviving unique tokens as a Python `frozenset`. The
//! outer list order matches the input order.
//!
//! ## Byte-for-byte parity (port note)
//!
//! This is a deterministic finite-state tokenizer: pure byte scanning, no
//! hashing of business interest, no floating point, no locale, no randomness.
//! So byte-for-byte parity with the C++ kernel and the pure-Python regex
//! reference (`backend/apps/pipeline/services/text_tokens.py`,
//! `TOKEN_RE = [A-Za-z0-9]+(?:'[A-Za-z0-9]+)?` + stopword removal) is fully
//! achievable and is the stated contract. The tokenizer feeds the
//! `keyword_jaccard` ranking signal, so exact token equality across the Python
//! reference and the native kernel is load-bearing.
//!
//! Scanning is over `text.as_bytes()`, NOT Rust `char` iteration, so non-ASCII
//! UTF-8 bytes act as separators identically to the C++ `std::string` byte
//! loop. `ascii_lower` lowercases only `A-Z`; every other byte is left
//! unchanged. See the port spec
//! `backend/tmp/port-specs/texttok.json`.
//!
//! ## Return type (load-bearing)
//!
//! The inner result MUST be a Python `frozenset` (`PyFrozenSet`), not a `set`
//! and not a `list`: callers do `frozenset` set operations for Jaccard overlap
//! and `tokenize_text()` indexes element `[0]` of the returned list. The outer
//! container is a Python `list` whose length equals `len(texts)`.

use std::collections::HashSet;
use std::hash::BuildHasher;

use pyo3::prelude::*;
use pyo3::types::{PyFrozenSet, PyList};

/// `true` when `byte` is ASCII alphanumeric `[0-9A-Za-z]`. Everything else is a
/// token separator. Mirrors the C++ `is_ascii_alnum(char)`.
#[inline]
const fn is_ascii_alnum(byte: u8) -> bool {
    byte.is_ascii_alphanumeric()
}

/// ASCII-lowercase a single byte: `A-Z` maps to `a-z`, every other byte is
/// returned unchanged. Mirrors the C++ `ascii_lower(char)` (it does NOT touch
/// non-ASCII bytes, so UTF-8 continuation bytes pass through untouched).
#[inline]
const fn ascii_lower(byte: u8) -> u8 {
    byte.to_ascii_lowercase()
}

/// Tokenize one text into its set of unique lowercased non-stopword tokens.
///
/// Plain Rust, unit-testable without Python. Operates on BYTES
/// (`text.as_bytes()`) to match the C++ byte-level scanning exactly. The
/// algorithm, byte-for-byte with `tokenize_one_core` in the C++ kernel:
///
/// 1. Skip any byte that is not ASCII alnum.
/// 2. Consume a run of ASCII alnum bytes, lowercasing each into the token.
/// 3. Apostrophe rule: if `index + 1 < len` and the next byte is `'` and the
///    byte after it is ASCII alnum, append the `'` and consume one more alnum
///    run (also lowercased). Exactly ONE apostrophe group is folded in; a
///    trailing apostrophe with no following alnum is not included.
/// 4. If the token is non-empty and not a stopword, insert it.
///
/// The stopword set is compared against the already-lowercased token using the
/// stopword strings AS PROVIDED (callers pass an already-lowercase list); the
/// kernel does NOT lowercase the stopwords itself.
///
/// Generic over the stopword set's `BuildHasher` (`S`) so any `HashSet<String>`
/// — whatever hasher the caller built it with — is accepted without forcing a
/// rebuild (`clippy::implicit_hasher`). The returned set uses the default
/// hasher.
#[must_use]
pub fn tokenize_one_core<S: BuildHasher>(
    text: &str,
    stopwords: &HashSet<String, S>,
) -> HashSet<String> {
    let bytes = text.as_bytes();
    let text_len = bytes.len();
    let mut unique_tokens: HashSet<String> = HashSet::new();
    let mut index = 0usize;

    while index < text_len {
        if !is_ascii_alnum(bytes[index]) {
            index += 1;
            continue;
        }

        let mut token = String::new();
        while index < text_len && is_ascii_alnum(bytes[index]) {
            token.push(ascii_lower(bytes[index]) as char);
            index += 1;
        }

        // Apostrophe / contraction rule. The `index + 1 < text_len` guard
        // matches the C++ `index + 1 < size` check: there must be at least one
        // alnum byte AFTER the apostrophe for it to be folded in.
        if index + 1 < text_len && bytes[index] == b'\'' && is_ascii_alnum(bytes[index + 1]) {
            token.push('\'');
            index += 1;
            while index < text_len && is_ascii_alnum(bytes[index]) {
                token.push(ascii_lower(bytes[index]) as char);
                index += 1;
            }
        }

        if !token.is_empty() && !stopwords.contains(&token) {
            unique_tokens.insert(token);
        }
    }

    unique_tokens
}

/// Tokenize a batch of texts, preserving input order.
///
/// Plain Rust, used by both the Criterion benchmark and the `PyO3` boundary. Generic over the stopword hasher for the same reason as [`tokenize_one_core`].
#[must_use]
pub fn tokenize_text_batch_core<S: BuildHasher>(
    texts: &[String],
    stopwords: &HashSet<String, S>,
) -> Vec<HashSet<String>> {
    texts
        .iter()
        .map(|text| tokenize_one_core(text, stopwords))
        .collect()
}

/// `tokenize_text_batch(texts: list[str], stopwords: Iterable[str]) -> list[frozenset[str]]`.
///
/// Builds the stopword lookup by iterating the `stopwords` iterable once and
/// extracting a `String` from each item (a non-str item raises `TypeError`,
/// matching the C++ `py::cast<std::string>` failure). For each input text it
/// builds a Python `frozenset` of the surviving tokens and appends it to a
/// Python `list`, in input order.
#[pyfunction]
#[pyo3(signature = (texts, stopwords))]
fn tokenize_text_batch<'py>(
    py: Python<'py>,
    texts: Vec<String>,
    stopwords: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyList>> {
    let mut stopword_lookup: HashSet<String> = HashSet::new();
    for item in stopwords.try_iter()? {
        let word: String = item?.extract()?;
        stopword_lookup.insert(word);
    }

    let results = PyList::empty(py);
    // Consume `texts` (it is not retained past this loop), which also satisfies
    // `clippy::needless_pass_by_value` for the by-value `Vec<String>` argument.
    for text in texts {
        let tokens = tokenize_one_core(&text, &stopword_lookup);
        let token_set = PyFrozenSet::new(py, tokens.iter())?;
        results.append(token_set)?;
    }
    Ok(results)
}

/// The Python module definition. The module name (`texttok`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`texttok.so`) imports as
/// `extensions.texttok` once staged on `PYTHONPATH` under `extensions/`.
/// Registering `tokenize_text_batch` keeps the health probe's expected
/// attribute present.
#[pymodule]
fn texttok(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(tokenize_text_batch, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{tokenize_one_core, tokenize_text_batch_core};
    use std::collections::HashSet;

    fn stopwords(words: &[&str]) -> HashSet<String> {
        words.iter().map(|w| (*w).to_string()).collect()
    }

    fn tokens(text: &str, stops: &[&str]) -> HashSet<String> {
        tokenize_one_core(text, &stopwords(stops))
    }

    fn sorted(set: HashSet<String>) -> Vec<String> {
        let mut v: Vec<String> = set.into_iter().collect();
        v.sort();
        v
    }

    #[test]
    fn lowercases_and_splits_on_non_alnum() {
        // Behavioural contract: split on non-[0-9A-Za-z], ASCII-lowercase.
        assert_eq!(
            sorted(tokens("Hello, World! 42", &[])),
            vec!["42".to_string(), "hello".to_string(), "world".to_string()]
        );
    }

    #[test]
    fn drops_stopwords_after_lowercasing() {
        // Stopword comparison is on the already-lowercased token.
        let out = sorted(tokens("The Quick brown FOX", &["the", "fox"]));
        assert_eq!(out, vec!["brown".to_string(), "quick".to_string()]);
    }

    #[test]
    fn deduplicates_repeated_tokens() {
        // Per-text result is a SET: duplicates collapse.
        assert_eq!(
            sorted(tokens("dog dog DOG Dog", &[])),
            vec!["dog".to_string()]
        );
    }

    #[test]
    fn folds_one_apostrophe_contraction() {
        // don't -> single token "don't"; you've -> "you've".
        assert_eq!(
            sorted(tokens("don't you've", &[])),
            vec!["don't".to_string(), "you've".to_string()]
        );
    }

    #[test]
    fn stopword_match_on_contraction() {
        // The contraction "don't" is itself a stopword in the real list.
        assert!(tokens("don't run", &["don't"]).contains("run"));
        assert!(!tokens("don't run", &["don't"]).contains("don't"));
    }

    #[test]
    fn trailing_apostrophe_not_included() {
        // A trailing apostrophe with no following alnum is NOT folded in
        // (boundary mutant: index+1 < size guard). "dogs'" -> "dogs".
        assert_eq!(sorted(tokens("dogs'", &[])), vec!["dogs".to_string()]);
    }

    #[test]
    fn apostrophe_at_end_of_text_boundary() {
        // The very last byte being an apostrophe must not over-read
        // (index+1 < text_len guard). "cat'" -> "cat".
        assert_eq!(sorted(tokens("cat'", &[])), vec!["cat".to_string()]);
    }

    #[test]
    fn apostrophe_followed_by_non_alnum_not_folded() {
        // "it's, ok" — the apostrophe after "it" is followed by 's' (alnum) so
        // "it's" folds; but "rock' n" has apostrophe followed by space, so
        // "rock" and "n" stay separate.
        assert_eq!(
            sorted(tokens("rock' n", &[])),
            vec!["n".to_string(), "rock".to_string()]
        );
    }

    #[test]
    fn only_one_apostrophe_group_consumed() {
        // Only ONE optional apostrophe group per token. "a'b'c" -> the first
        // run "a" + first apostrophe group "b" => "a'b"; then a second
        // apostrophe with following alnum "c" starts a fresh token boundary?
        // No: after "a'b" the scanner is at the second apostrophe. The C++
        // outer loop sees that apostrophe is not alnum, skips it, then reads
        // "c" as a new token. So tokens are {"a'b", "c"}.
        assert_eq!(
            sorted(tokens("a'b'c", &[])),
            vec!["a'b".to_string(), "c".to_string()]
        );
    }

    #[test]
    fn non_ascii_bytes_act_as_separators() {
        // Byte-level scan: a multi-byte UTF-8 char (é = 0xC3 0xA9) is two
        // non-alnum bytes, so it splits "caf" and "" — "café" -> "caf".
        assert_eq!(sorted(tokens("café", &[])), vec!["caf".to_string()]);
    }

    #[test]
    fn empty_text_yields_empty_set() {
        assert!(tokens("", &[]).is_empty());
        assert!(tokens("!!!   ...", &[]).is_empty());
    }

    #[test]
    fn batch_preserves_order_and_per_text_sets() {
        let texts = vec![
            "Hello world".to_string(),
            String::new(),
            "Foo foo BAR".to_string(),
        ];
        let out = tokenize_text_batch_core(&texts, &stopwords(&["bar"]));
        assert_eq!(out.len(), 3);
        assert_eq!(
            sorted(out[0].clone()),
            vec!["hello".to_string(), "world".to_string()]
        );
        assert!(out[1].is_empty());
        assert_eq!(sorted(out[2].clone()), vec!["foo".to_string()]);
    }

    #[test]
    fn digits_are_tokens() {
        // [0-9] are alnum; "year 2024" -> {"year", "2024"}.
        assert_eq!(
            sorted(tokens("year 2024", &[])),
            vec!["2024".to_string(), "year".to_string()]
        );
    }
}
