//! Anchor self-information hot-path kernel, ported from the former C++
//! `anchor_self_information` kernel to Rust and exposed to Python as the
//! native module `extensions.anchor_self_information` via `PyO3`.
//!
//! The kernel computes the Shannon entropy of the distribution of adjacent
//! BYTE pairs (bigrams) of an input string:
//!
//! ```text
//! H(X) = -SUM p(x) * log2(p(x))   (in bits)
//! ```
//!
//! where the sum runs over every distinct byte-bigram and `p(x)` is that
//! bigram's relative frequency. This is Shannon's entropy of an information
//! source (Shannon, C. E. (1948), "A Mathematical Theory of Communication",
//! Bell System Technical Journal 27(3+4), Section 9). The result feeds an
//! Iglewicz-Hoaglin (1993) modified z-score anomaly detector in
//! `apps/pipeline/services/anchor_garbage_signals.py`.
//!
//! ## Byte bigrams, not char bigrams (port note)
//!
//! The C++ kernel packed the two RAW BYTES of `text[i]` and `text[i+1]` into a
//! `uint16` key, so it counted BYTE bigrams. For multi-byte UTF-8 input this
//! differs subtly from the pure-Python fallback (which counts CHARACTER
//! bigrams via `text[i:i+2]`); for ASCII the two are identical. This Rust port
//! reproduces the C++ BYTE-bigram behaviour — it iterates over
//! `text.as_bytes()` and pairs adjacent bytes — so the kernel keeps producing
//! the same entropy the running system already persisted as corpus
//! median/MAD statistics. Iterating over Rust `char`s (Unicode scalar values)
//! would change the entropy of non-ASCII anchors and shift those statistics.
//!
//! ## Parity basis (port note)
//!
//! The math is fully deterministic, but `HashMap` iteration order in Rust
//! differs from `std::unordered_map` in C++. The entropy is a sum over the
//! bigram multiset and floating-point `+` is commutative to within last-bit
//! rounding, so the two implementations agree to a small float tolerance, not
//! byte-for-byte. No Python caller depends on a byte-exact `f64`: every caller
//! routes through `_bigram_entropy`, which wraps the value in `float()` and
//! feeds it to the median/MAD score. The contract that must hold is identical
//! byte-bigram semantics, the exact `0.0` boundary behaviour for inputs
//! shorter than two bytes, and entropy agreement within `1e-9`.

use std::collections::HashMap;

use pyo3::prelude::*;

/// Plain-Rust Shannon byte-bigram entropy core over a byte slice (no `PyO3`).
///
/// Counts every distinct adjacent byte pair (bigram) of `bytes`, packing the
/// two bytes into a `u16` key `(a << 8) | b` exactly like the C++ kernel's
/// `uint16` key, then returns `-SUM p * log2(p)` in bits. All logic lives here
/// so it is unit-testable with `cargo test` and benchable with Criterion
/// without crossing the Python boundary (matching the
/// `CountMinSketchCore` / `normalize_l2_slice` reference pattern).
///
/// Guarantees: a slice shorter than two bytes returns exactly `0.0` (no
/// bigrams to count); the result is always non-negative; it equals `0.0`
/// exactly when every bigram is identical (a single distinct bigram); `N`
/// distinct equiprobable bigrams return `log2(N)` bits; and the result is a
/// pure deterministic function of the input bytes (the entropy is a sum over
/// the bigram multiset, so iteration order does not change the mathematical
/// value).
#[must_use]
pub fn bigram_entropy_bytes(bytes: &[u8]) -> f64 {
    let n = bytes.len();
    if n < 2 {
        return 0.0;
    }
    // Key is the packed (a << 8) | b byte pair, matching the C++ uint16 key.
    let mut counts: HashMap<u16, u32> = HashMap::with_capacity(n);
    let mut total: u32 = 0;
    for window in bytes.windows(2) {
        let a = u16::from(window[0]);
        let b = u16::from(window[1]);
        let key = (a << 8) | b;
        *counts.entry(key).or_insert(0) += 1;
        total += 1;
    }
    if total == 0 {
        // Defensive: unreachable when `n >= 2` (there is always at least one
        // length-2 window), but mirrors the C++ kernel's `total == 0` guard.
        return 0.0;
    }
    let inv_total = 1.0 / f64::from(total);
    let mut h = 0.0_f64;
    for &count in counts.values() {
        // Every counted bigram was incremented at least once, so `count >= 1`
        // and `p > 0`, which makes `log2(p)` always well-defined and finite.
        let p = f64::from(count) * inv_total;
        h -= p * p.log2();
    }
    h
}

/// `bigram_entropy(text) -> float` — Shannon byte-bigram entropy of `text` in
/// bits.
///
/// Operates on the UTF-8 *bytes* of `text` (not its `char`s), so it reproduces
/// the C++ kernel's byte-bigram semantics. Takes a single required `str`
/// argument named `text` (matching the C++ `py::arg("text")`) and returns an
/// `f64`. It raises no exception of its own; the only failure mode is the
/// standard `str`-extraction `TypeError` `PyO3` raises when a non-`str` is
/// passed, which matches the original pybind11 behaviour.
#[pyfunction(signature = (text))]
#[pyo3(text_signature = "(text)")]
fn bigram_entropy(text: &str) -> f64 {
    bigram_entropy_bytes(text.as_bytes())
}

/// The Python module definition. The module name (`anchor_self_information`)
/// MUST match the `[lib] name` in `Cargo.toml` so the built artifact
/// (`anchor_self_information.so`) imports as
/// `extensions.anchor_self_information` once it is staged on `PYTHONPATH` under
/// `extensions/`. Registering the `bigram_entropy` function keeps the native
/// runtime health probe's expected attribute
/// (`anchor_self_information.bigram_entropy`, health.py line 52) present.
#[pymodule]
fn anchor_self_information(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add(
        "__doc__",
        "Shannon byte-bigram entropy for anchor self-information.",
    )?;
    m.add_function(wrap_pyfunction!(bigram_entropy, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    // The boundary cases (inputs shorter than two bytes, a single repeated
    // bigram) return entropy that is *exactly* 0.0 by construction — no
    // floating-point rounding can occur because the only term is
    // -1.0 * log2(1.0), which is exactly 0.0, or the early-return literal 0.0.
    // A strict `==` is the correct assertion there; an epsilon would hide a
    // regression that nudged an "exactly zero" result off zero. Allow clippy's
    // pedantic `float_cmp` for these intentional exact boundary checks, exactly
    // as the l2norm reference port does for its sub-threshold no-op rows.
    #![allow(clippy::float_cmp)]

    use super::bigram_entropy_bytes;

    /// Float tolerance for entropy assertions, per the spec's parity basis
    /// (`1e-9` absolute). Exact `==` is used only for the `0.0` boundary cases.
    const TOL: f64 = 1e-9;

    #[test]
    fn empty_string_returns_exactly_zero() {
        // Fewer than two bytes -> no bigrams -> exactly 0.0. Boundary case, so
        // an exact comparison is correct (no rounding can occur).
        assert_eq!(bigram_entropy_bytes(b""), 0.0);
    }

    #[test]
    fn single_byte_returns_exactly_zero() {
        // One byte is still fewer than two bytes -> the `n < 2` guard returns
        // 0.0. Pins the boundary to `< 2`: a `< 1` mutant would wrongly try to
        // form a bigram from a single byte.
        assert_eq!(bigram_entropy_bytes(b"a"), 0.0);
    }

    #[test]
    fn two_identical_bytes_return_exactly_zero() {
        // Exactly one bigram ("aa"), so p = 1.0 and -1*log2(1) = 0. A single
        // distinct bigram has zero entropy. Exact comparison: the only term is
        // -1.0 * log2(1.0) which is exactly 0.0.
        assert_eq!(bigram_entropy_bytes(b"aa"), 0.0);
    }

    #[test]
    fn single_repeated_bigram_returns_zero() {
        // "aaaa" -> bigrams {"aa","aa","aa"} -> one distinct bigram, p=1.0.
        // Entropy is 0.0 iff every bigram is identical (contract guarantee 2).
        assert!(bigram_entropy_bytes(b"aaaa").abs() < TOL);
    }

    #[test]
    fn two_equiprobable_distinct_bigrams_return_one_bit() {
        // "abab" -> bigrams "ab","ba","ab" ... wait: spell it out so the count
        // is exactly two distinct bigrams each appearing once. "abcd" gives
        // bigrams "ab","bc","cd" (3 distinct). For exactly two equiprobable
        // bigrams use "abab": windows are "ab","ba","ab" -> {"ab":2,"ba":1},
        // NOT equiprobable. Use "abcdab"? Simpler: a 4-byte string whose two
        // bigrams are distinct and each occurs once: bytes [0,1, 2,3] would be
        // "ab","b?"... windows overlap. To get two NON-overlapping-effect
        // equiprobable bigrams, hand-build counts via a string whose window
        // multiset is exactly {X:1, Y:1}. "abca" -> "ab","bc","ca" = 3 distinct
        // single counts -> log2(3). For exactly two, the cleanest is a string
        // of length 3 with distinct overlapping bigrams: "abc" -> "ab","bc" ->
        // two distinct bigrams, each count 1 -> H = log2(2) = 1.0 bit.
        let h = bigram_entropy_bytes(b"abc");
        assert!((h - 1.0).abs() < TOL, "expected 1.0 bit, got {h}");
    }

    #[test]
    fn n_equiprobable_distinct_bigrams_return_log2_n() {
        // A string of N+1 strictly increasing distinct bytes yields N distinct
        // overlapping bigrams, each occurring exactly once -> H = log2(N).
        // Contract guarantee 3. Bytes 0..=8 (9 bytes) -> 8 distinct bigrams ->
        // log2(8) = 3.0 bits.
        let bytes: Vec<u8> = (0u8..=8).collect();
        let h = bigram_entropy_bytes(&bytes);
        assert!((h - 3.0).abs() < TOL, "expected log2(8)=3.0, got {h}");
    }

    #[test]
    fn known_two_to_one_distribution_matches_hand_computed_value() {
        // "aaab" -> windows "aa","aa","ab" -> counts {"aa":2,"ab":1}, total 3.
        // H = -(2/3)log2(2/3) - (1/3)log2(1/3)
        //   =  (2/3)log2(3/2)  + (1/3)log2(3)  = 0.9182958340544896 bits.
        let h = bigram_entropy_bytes(b"aaab");
        let expected = -(2.0 / 3.0) * (2.0_f64 / 3.0).log2() - (1.0 / 3.0) * (1.0_f64 / 3.0).log2();
        assert!((h - expected).abs() < TOL, "got {h}, expected {expected}");
        // And the literal hand-computed value, so a refactor of `expected`
        // cannot silently drift.
        assert!(
            (h - 0.918_295_834_054_489_6).abs() < TOL,
            "got {h}, expected 0.9182958340544896"
        );
    }

    #[test]
    fn result_is_always_non_negative() {
        // Contract guarantee: entropy is non-negative for any input.
        for sample in [
            b"".as_slice(),
            b"x",
            b"xy",
            b"hello world",
            b"\x00\xff\x00\xff",
        ] {
            assert!(
                bigram_entropy_bytes(sample) >= 0.0,
                "entropy went negative for {sample:?}"
            );
        }
    }

    #[test]
    fn result_is_order_independent_over_the_bigram_multiset() {
        // Order-independence: the same byte multiset of bigrams yields the same
        // entropy regardless of summation order. Rust's `HashMap` uses a
        // per-instance random seed, so two separate calls sum the p*log2(p)
        // terms in different orders and can differ in the last float bit (the
        // parity basis the spec calls out). The mathematical value is identical,
        // so the two runs must agree within the 1e-9 tolerance — not byte-for-
        // byte. Asserting `< TOL` (not `==`) is the correct contract.
        let a = bigram_entropy_bytes(b"the quick brown fox jumps over the lazy dog");
        let b = bigram_entropy_bytes(b"the quick brown fox jumps over the lazy dog");
        assert!(
            (a - b).abs() < TOL,
            "entropy must agree within tolerance across runs: {a} vs {b}"
        );
    }

    #[test]
    fn counts_bytes_not_chars_for_multibyte_utf8() {
        // The euro sign 'EUR' (U+20AC) is the 3-byte UTF-8 sequence
        // E2 82 AC. The 2-char string "EURa" (euro + 'a') is bytes
        // [E2, 82, AC, 61] -> 3 byte-bigrams: (E2,82),(82,AC),(AC,61), all
        // distinct, each count 1 -> H = log2(3). A CHAR-based implementation
        // would instead see 2 chars -> 1 char-bigram -> H = 0.0. Asserting
        // log2(3) proves the port counts BYTES, not chars (the key port
        // requirement). This kills any `.chars()`-vs-`.as_bytes()` mutant.
        let euro_a = "\u{20AC}a";
        let h = bigram_entropy_bytes(euro_a.as_bytes());
        let expected = 3.0_f64.log2();
        assert!(
            (h - expected).abs() < TOL,
            "byte-bigram entropy of '{euro_a}' should be log2(3)={expected}, got {h}"
        );
        // Sanity: there really are 4 bytes but only 2 chars.
        assert_eq!(euro_a.len(), 4);
        assert_eq!(euro_a.chars().count(), 2);
    }

    #[test]
    fn high_bytes_do_not_alias_via_sign_extension() {
        // Bytes >= 0x80 must widen to u16 without sign trouble (the C++ used
        // unsigned char widening). 0x80,0xFF,0x80,0xFF -> windows
        // (80,FF),(FF,80),(80,FF) -> counts {(80FF):2,(FF80):1}, total 3 ->
        // same distribution as "aaab" above -> 0.9182958340544896 bits.
        let h = bigram_entropy_bytes(&[0x80, 0xFF, 0x80, 0xFF]);
        assert!(
            (h - 0.918_295_834_054_489_6).abs() < TOL,
            "high-byte bigrams gave {h}, expected 0.9182958340544896"
        );
    }
}
