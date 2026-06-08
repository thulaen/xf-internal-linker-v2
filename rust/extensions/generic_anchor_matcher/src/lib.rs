//! Aho-Corasick generic-anchor matcher hot-path kernel, ported from the C++
//! `generic_anchor_matcher` kernel
//! (`backend/extensions/generic_anchor_matcher.cpp`) to Rust and exposed to
//! Python as the native module `extensions.generic_anchor_matcher` via `PyO3`.
//!
//! An Aho-Corasick automaton (Aho, A. V., & Corasick, M. J. 1975, "Efficient
//! String Matching: An Aid to Bibliographic Search", Communications of the ACM
//! 18(6):333-340) is built from a list of generic-anchor phrases and matches an
//! input string against every phrase in a single linear pass.
//!
//! The Python-callable API matches the C++ kernel exactly:
//!
//! - class `Automaton` — opaque handle, constructed only via `build_automaton`.
//!   Exposes the read-only `node_count: int` attribute and the
//!   `phrase_count() -> int` method.
//! - `build_automaton(phrases: list[str]) -> Automaton`.
//! - `find_all(automaton: Automaton, text: str) -> list[str]` — the distinct
//!   phrases that occur as byte-substrings of `text`, each emitted once, in the
//!   order of the first text byte position at which the phrase is encountered.
//!
//! ## Byte-for-byte parity (port note)
//!
//! This kernel uses zero hashing and zero floating-point — it is pure
//! integer/string logic over the raw UTF-8 bytes of each string with a 256-byte
//! per-phrase cap. So byte-for-byte parity with the C++ kernel and the
//! pure-Python fallback (`anchor_garbage_signals.py::_python_find_all`) is fully
//! achievable and is the stated contract. Matching is over `as_bytes()`, NOT
//! Rust `char` boundaries, so non-ASCII UTF-8 substrings match exactly as the
//! C++ `std::string`/byte loop did. See `docs/specs/` and the port spec
//! `backend/tmp/port-specs/generic_anchor_matcher.json`.
//!
//! ## Index types (no signed casts)
//!
//! Node ids and phrase indices are unsigned: node ids are `usize` with the
//! sentinel `NO_TRANSITION = usize::MAX` for "no goto edge", and phrase indices
//! are `u32` (the C++ kernel used `int32` phrase indices; `u32` covers the same
//! lexicon sizes without any signed-to-unsigned cast). Using unsigned types
//! throughout removes every `as usize` sign-loss cast while keeping behaviour
//! identical: the root is node `0`, a missing edge is `usize::MAX`, and the
//! self-loop trick still makes the match scan branchless on bounds.

use pyo3::prelude::*;

/// Per-phrase byte-length cap. Phrases longer than this (in BYTES) are skipped
/// from the trie but still counted by `phrase_count()`, matching the C++
/// `max_phrase_len`.
const MAX_PHRASE_LEN: usize = 256;

/// 256-way alphabet (one slot per byte value).
const ALPHABET_SIZE: usize = 256;

/// Sentinel node id meaning "no transition" in the flat goto table (the C++
/// `no_transition`, here the maximum `usize` so no valid node id collides).
const NO_TRANSITION: usize = usize::MAX;

/// The root node id. The trie root is always node 0.
const ROOT: usize = 0;

/// Flat index into the goto table for `(node, byte)`: `(node << 8) | byte`,
/// matching the C++ `goto_index`.
#[inline]
fn goto_index(node: usize, byte: u8) -> usize {
    (node << 8) | (byte as usize)
}

/// Plain-Rust Aho-Corasick automaton core (no `PyO3`).
///
/// Mirrors the C++ `Automaton` struct field-for-field so the build and match
/// produce byte-identical results:
/// - `goto_table`: flat `node_count * 256` transition table of node ids.
/// - `fail_link`: per-node failure link (a node id).
/// - `output`: phrase indices terminating at each node (own terminals in
///   trie-insertion order, then inherited fail-link outputs).
/// - `phrases`: every input phrase in insertion order (including skipped ones).
/// - `node_count`: number of trie nodes; the root is node 0, so a fresh empty
///   automaton has `node_count == 1`.
///
/// All logic lives here so it is unit-testable with `cargo test` without
/// crossing the Python boundary.
pub struct AutomatonCore {
    goto_table: Vec<usize>,
    fail_link: Vec<usize>,
    output: Vec<Vec<u32>>,
    phrases: Vec<String>,
    node_count: usize,
}

impl AutomatonCore {
    /// Build the automaton from `phrases`, consuming the vector.
    ///
    /// Each phrase is kept in `phrases` in insertion order regardless of whether
    /// it is inserted into the trie. An empty phrase, or a phrase whose BYTE
    /// length exceeds [`MAX_PHRASE_LEN`], is skipped from the trie but still
    /// counted (so `phrase_count()` equals `phrases.len()` and phrase indices
    /// stay aligned with the input list). Accepts an empty list.
    ///
    /// # Panics
    ///
    /// Panics only if the lexicon contains more than `u32::MAX` (~4.29 billion)
    /// phrases, which cannot occur for any realistic anchor lexicon. The C++
    /// kernel used `int32` phrase indices, so this is the same practical bound.
    #[must_use]
    pub fn build(phrases: Vec<String>) -> Self {
        // Root node: 256 slots, all NO_TRANSITION. fail_link[root] = root (0),
        // output[root] empty.
        let mut aut = Self {
            goto_table: vec![NO_TRANSITION; ALPHABET_SIZE],
            fail_link: vec![ROOT],
            output: vec![Vec::new()],
            phrases: Vec::new(),
            node_count: 1,
        };

        for (i, p) in phrases.into_iter().enumerate() {
            let bytes_len = p.len();
            if bytes_len == 0 || bytes_len > MAX_PHRASE_LEN {
                // Skip pathological inputs but still record the phrase so output
                // positions stay aligned with the input list.
                aut.phrases.push(p);
                continue;
            }
            // `i` fits in u32 for any realistic lexicon; the C++ kernel used
            // i32 phrase indices, so u32 reproduces that exactly. Insert before
            // moving the phrase into `phrases`.
            let phrase_idx = u32::try_from(i).expect("phrase index exceeds u32::MAX");
            aut.insert_phrase(phrase_idx, p.as_bytes());
            aut.phrases.push(p);
        }
        aut.build_fail_links();
        aut
    }

    /// Insert `phrase` (raw bytes) into the trie, recording `phrase_idx` in the
    /// terminal node's output list.
    fn insert_phrase(&mut self, phrase_idx: u32, phrase: &[u8]) {
        let mut node = ROOT;
        for &byte in phrase {
            let idx = goto_index(node, byte);
            if self.goto_table[idx] == NO_TRANSITION {
                self.goto_table[idx] = self.node_count;
                // Grow the flat tables for the new node (256 fresh slots).
                let new_len = self.goto_table.len() + ALPHABET_SIZE;
                self.goto_table.resize(new_len, NO_TRANSITION);
                self.fail_link.push(ROOT);
                self.output.push(Vec::new());
                self.node_count += 1;
            }
            node = self.goto_table[idx];
        }
        self.output[node].push(phrase_idx);
    }

    /// Build failure links by BFS per Aho-Corasick 1975 §2, and inherit output
    /// sets along the fail links. Missing root transitions self-loop on the root
    /// so the match scan never needs an explicit bounds check.
    fn build_fail_links(&mut self) {
        let mut queue: std::collections::VecDeque<usize> = std::collections::VecDeque::new();

        // First-level nodes: fail link is the root; missing root transitions
        // self-loop on the root. Iterate over every byte value 0..=255 (the
        // full alphabet) directly, so there is no `usize`->`u8` cast.
        for byte in 0..=u8::MAX {
            let child = self.goto_table[goto_index(ROOT, byte)];
            if child == NO_TRANSITION {
                self.goto_table[goto_index(ROOT, byte)] = ROOT;
            } else {
                self.fail_link[child] = ROOT;
                queue.push_back(child);
            }
        }

        while let Some(node) = queue.pop_front() {
            for byte in 0..=u8::MAX {
                let child = self.goto_table[goto_index(node, byte)];
                if child == NO_TRANSITION {
                    continue;
                }
                // Fail link of child = goto[fail[node], byte]; walk up failure
                // links until the byte transition exists (root self-loops
                // guarantee termination).
                let mut f = self.fail_link[node];
                while f != ROOT && self.goto_table[goto_index(f, byte)] == NO_TRANSITION {
                    f = self.fail_link[f];
                }
                let link = self.goto_table[goto_index(f, byte)];
                // Don't link a node to itself.
                let resolved = if link == child { ROOT } else { link };
                self.fail_link[child] = resolved;
                // Inherit output from the fail link.
                let parent_out = self.output[resolved].clone();
                self.output[child].extend(parent_out);
                queue.push_back(child);
            }
        }
    }

    /// Return the distinct phrases occurring as byte-substrings of `text`, each
    /// emitted once, in the order of the FIRST text byte position at which the
    /// phrase's index is encountered during the left-to-right scan.
    ///
    /// Returns an empty list when `text` is empty or the automaton has zero
    /// phrases (the null-handle case is handled at the `PyO3` boundary).
    #[must_use]
    pub fn find_all(&self, text: &str) -> Vec<String> {
        let mut out: Vec<String> = Vec::new();
        if text.is_empty() || self.phrases.is_empty() {
            return out;
        }
        // `seen` de-duplicates by phrase index so each distinct phrase is
        // emitted exactly once, on first match position.
        let mut seen: std::collections::HashSet<u32> =
            std::collections::HashSet::with_capacity(self.phrases.len());
        let mut node = ROOT;
        for &byte in text.as_bytes() {
            // Follow goto / fail until we land on a transition (root self-loops
            // guarantee termination).
            while node != ROOT && self.goto_table[goto_index(node, byte)] == NO_TRANSITION {
                node = self.fail_link[node];
            }
            let next = self.goto_table[goto_index(node, byte)];
            if next != NO_TRANSITION {
                node = next;
            }
            for &phrase_idx in &self.output[node] {
                if seen.insert(phrase_idx) {
                    out.push(self.phrases[phrase_idx as usize].clone());
                }
            }
        }
        out
    }

    /// The number of trie nodes (root is node 0, so a fresh empty automaton has
    /// `node_count == 1`).
    #[must_use]
    pub fn node_count(&self) -> usize {
        self.node_count
    }

    /// The number of phrases passed to `build` (including skipped empty/over-cap
    /// ones), matching the C++ `phrases.size()`.
    #[must_use]
    pub fn phrase_count(&self) -> usize {
        self.phrases.len()
    }
}

/// Python-facing opaque automaton handle. Thin wrapper around [`AutomatonCore`]
/// constructed only via [`build_automaton`] and passed back into [`find_all`].
#[pyclass]
pub struct Automaton {
    core: AutomatonCore,
}

#[pymethods]
impl Automaton {
    /// Read-only `node_count` attribute (root counts as node 0).
    #[getter]
    fn node_count(&self) -> usize {
        self.core.node_count()
    }

    /// `phrase_count() -> int` — number of input phrases (including skipped).
    fn phrase_count(&self) -> usize {
        self.core.phrase_count()
    }
}

/// `build_automaton(phrases: list[str]) -> Automaton`.
///
/// Accepts an empty list (returns an automaton with `node_count == 1`,
/// `phrase_count() == 0`). Never raises for any input list.
#[pyfunction]
#[pyo3(signature = (phrases))]
fn build_automaton(phrases: Vec<String>) -> Automaton {
    Automaton {
        core: AutomatonCore::build(phrases),
    }
}

/// `find_all(automaton: Automaton, text: str) -> list[str]`.
///
/// Returns the distinct phrases occurring as byte-substrings of `text`, each
/// once, in first-match-position order. Returns `[]` for empty `text` or an
/// automaton with zero phrases. Never raises for any valid `(Automaton, str)`.
#[pyfunction]
#[pyo3(signature = (automaton, text))]
fn find_all(automaton: &Automaton, text: &str) -> Vec<String> {
    automaton.core.find_all(text)
}

/// The Python module definition. The module name (`generic_anchor_matcher`)
/// MUST match the `[lib] name` in `Cargo.toml` so the built artifact
/// (`generic_anchor_matcher.so`) imports as `extensions.generic_anchor_matcher`
/// once staged on `PYTHONPATH` under `extensions/`. Registering the `Automaton`
/// class and both functions keeps the health probe's expected attribute
/// (`build_automaton`) and the class attribute present.
#[pymodule]
fn generic_anchor_matcher(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<Automaton>()?;
    m.add_function(wrap_pyfunction!(build_automaton, m)?)?;
    m.add_function(wrap_pyfunction!(find_all, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::AutomatonCore;

    fn build(phrases: &[&str]) -> AutomatonCore {
        let owned: Vec<String> = phrases.iter().map(|s| (*s).to_string()).collect();
        AutomatonCore::build(owned)
    }

    #[test]
    fn empty_phrase_list_has_single_root_node_and_no_phrases() {
        // node_count == 1 (root only) and phrase_count == 0 for an empty list.
        // Kills a `node_count = 1 -> 0` init mutant.
        let aut = build(&[]);
        assert_eq!(aut.node_count(), 1);
        assert_eq!(aut.phrase_count(), 0);
        assert!(aut.find_all("anything").is_empty());
    }

    #[test]
    fn empty_text_returns_empty() {
        let aut = build(&["he", "she"]);
        assert!(aut.find_all("").is_empty());
    }

    #[test]
    fn zero_phrases_after_skip_returns_empty() {
        // A single empty phrase is skipped from the trie but still counted; with
        // no inserted phrase, find_all still scans but matches nothing.
        let aut = build(&[""]);
        assert_eq!(aut.phrase_count(), 1);
        assert_eq!(aut.node_count(), 1, "empty phrase must add no trie nodes");
        assert!(aut.find_all("hello").is_empty());
    }

    #[test]
    fn over_cap_phrase_skipped_from_matching_but_counted() {
        // A 257-byte phrase exceeds MAX_PHRASE_LEN (256): skipped from the trie
        // (no nodes added) but counted by phrase_count(). Kills a `> -> >=`
        // boundary mutant on the cap.
        let long = "a".repeat(257);
        let aut = build(&[&long]);
        assert_eq!(aut.phrase_count(), 1);
        assert_eq!(
            aut.node_count(),
            1,
            "over-cap phrase must add no trie nodes"
        );
        assert!(aut.find_all(&long).is_empty());
    }

    #[test]
    fn exactly_cap_length_phrase_is_inserted() {
        // A 256-byte phrase is at the cap and MUST be inserted (the boundary is
        // `> 256`, not `>= 256`). Kills the other side of the `> -> >=` mutant.
        let at_cap = "a".repeat(256);
        let aut = build(&[&at_cap]);
        assert_eq!(aut.phrase_count(), 1);
        assert!(aut.node_count() > 1, "256-byte phrase must add trie nodes");
        assert_eq!(aut.find_all(&at_cap), vec![at_cap]);
    }

    #[test]
    fn classic_aho_corasick_set_all_found() {
        // The canonical Aho-Corasick example set {he, she, his, hers}.
        let aut = build(&["he", "she", "his", "hers"]);
        let got = aut.find_all("ushers");
        // "ushers" contains: she (idx1), he (idx0), hers (idx3). First-match
        // position order: at byte 3 ('e' after 'sh') both "she" then "he" close;
        // "hers" closes later. So order is she, he, hers.
        assert_eq!(got, vec!["she", "he", "hers"]);
    }

    #[test]
    fn duplicate_match_emitted_once() {
        // The same phrase occurs twice in the text but is emitted exactly once
        // (seen-set). Kills a mutant that drops the de-dup guard.
        let aut = build(&["ab"]);
        assert_eq!(aut.find_all("ababab"), vec!["ab"]);
    }

    #[test]
    fn first_match_position_order_is_preserved() {
        // Distinct phrases are emitted in order of first match position.
        let aut = build(&["world", "hello"]);
        assert_eq!(aut.find_all("hello world"), vec!["hello", "world"]);
    }

    #[test]
    fn prefix_phrase_and_longer_phrase_both_reported() {
        // "an" is a prefix of "anchor"; both occur in the text and both report.
        let aut = build(&["an", "anchor"]);
        let got = aut.find_all("anchor");
        assert!(got.contains(&"an".to_string()));
        assert!(got.contains(&"anchor".to_string()));
        // "an" closes first (byte 1), "anchor" at byte 5.
        assert_eq!(got, vec!["an", "anchor"]);
    }

    #[test]
    fn non_ascii_utf8_substring_matches_byte_exact() {
        // Matching is over UTF-8 bytes, so a multi-byte character phrase matches
        // its exact byte sequence inside a larger string.
        let aut = build(&["café"]);
        assert_eq!(aut.find_all("the café opens"), vec!["café"]);
    }

    #[test]
    fn phrase_longer_than_text_not_matched() {
        let aut = build(&["abcdef"]);
        assert!(aut.find_all("abc").is_empty());
    }

    #[test]
    fn node_count_grows_by_distinct_trie_nodes() {
        // "ab" adds 2 nodes (a, ab); "ac" shares "a" and adds 1 (ac). Root is 1.
        // Total node_count == 1 + 2 + 1 == 4. Kills a node-count off-by-one.
        let aut = build(&["ab", "ac"]);
        assert_eq!(aut.node_count(), 4);
    }

    #[test]
    fn deterministic_across_two_builds() {
        let phrases = ["spam", "ham", "eggs", "spammer"];
        let a = build(&phrases);
        let b = build(&phrases);
        let text = "the spammer sells ham and eggs";
        assert_eq!(a.find_all(text), b.find_all(text));
    }

    #[test]
    fn no_false_positive_for_absent_phrase() {
        let aut = build(&["zzz"]);
        assert!(aut.find_all("the quick brown fox").is_empty());
    }
}
