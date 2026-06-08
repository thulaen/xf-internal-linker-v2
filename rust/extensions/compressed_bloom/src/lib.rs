//! Compressed Bloom filter hot-path kernel, ported from the C++
//! `compressed_bloom` kernel (`backend/extensions/compressed_bloom.cpp`) to
//! Rust and exposed to Python as the native module `extensions.compressed_bloom`
//! via `PyO3`.
//!
//! A Bloom filter (Bloom, B. H. 1970, "Space/Time Trade-offs in Hash Coding
//! with Allowable Errors", Communications of the ACM 13(7):422-426,
//! doi:10.1145/362686.362692) is a fixed-size bit array. `add` sets one bit per
//! hash function for an item; `contains` reports membership — true iff every
//! indexed bit is set. There is no `remove`: bits are never cleared, so a plain
//! Bloom filter never produces a false negative. False positives are expected
//! and bounded by the table load.
//!
//! The Python-callable API matches the C++ kernel exactly — a single class:
//!
//! - `CompressedBloomFilter(bit_count, hashes)` — raises `ValueError("bit_count
//!   and hashes must be positive")` when either argument is `0`.
//! - `add(item) -> None`.
//! - `contains(item) -> bool`.
//! - `bit_count() -> int`, `byte_count() -> int`, `hash_count() -> int`.
//!
//! ## Deliberate hashing decision (port note)
//!
//! The C++ kernel indexed bits with `std::hash<std::string>`, which is
//! libstdc++-implementation-defined, so the exact bit-to-index mapping was
//! never a portable cross-language contract. A repository-wide search found
//! zero Python callers of `add`/`contains`, so no caller depends on specific
//! hash outputs or specific bit layouts. This Rust port reproduces the
//! BEHAVIOURAL contract, not C++ hash bytes: no false negatives (a set bit is
//! never cleared, so a once-added item is `contains`-true forever),
//! determinism, the accessors, and the `bit_count == 0 || hashes == 0` guard.
//! It keeps the C++ salt design — `salt = i * 0x517cc1b727220a95` (a 64-bit odd
//! mixing multiplier) appended after a `#` separator — but hashes with a FIXED
//! deterministic hasher (`std::collections::hash_map::DefaultHasher`, the
//! standard library's `SipHash` with fixed default keys) so results are
//! reproducible across runs and machines for a given build, exactly like the
//! `count_min_sketch` and `counting_bloom` ports.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use xf_kernels::salted_index;

/// The 64-bit odd mixing multiplier used to decorrelate the per-hash salts,
/// matching the C++ kernel's `0x517cc1b727220a95ULL`.
const SALT_MIX: u64 = 0x517c_c1b7_2722_0a95;

/// Plain-Rust compressed Bloom filter core over native types (no `PyO3`).
///
/// Holds a flat `Vec<u8>` bit array of `ceil(bit_count / 8)` bytes, all zero at
/// construction, plus the configured `bit_count` and `hashes`. All logic lives
/// here so it is unit-testable with `cargo test` without crossing the Python
/// boundary.
pub struct CompressedBloomFilterCore {
    bits: Vec<u8>,
    bit_count: usize,
    hashes: usize,
}

impl CompressedBloomFilterCore {
    /// Construct a filter with `bit_count` bits (all zero) packed into
    /// `ceil(bit_count / 8)` bytes and `hashes` hash functions.
    ///
    /// # Errors
    ///
    /// Returns `Err` when `bit_count == 0` or `hashes == 0` — a filter needs at
    /// least one bit and one hash function. This mirrors the C++ kernel's
    /// `std::invalid_argument("bit_count and hashes must be positive")`.
    pub fn new(bit_count: usize, hashes: usize) -> Result<Self, &'static str> {
        if bit_count == 0 || hashes == 0 {
            return Err("bit_count and hashes must be positive");
        }
        Ok(Self {
            bits: vec![0; bit_count.div_ceil(8)],
            bit_count,
            hashes,
        })
    }

    /// Bit index for `item` under hash function `salt`.
    ///
    /// Delegates to the shared [`xf_kernels::salted_index`] helper, passing this
    /// kernel's own `SALT_MIX` constant and `bit_count` as the modulus.
    /// `bit_count >= 1` is guaranteed by `new`, so the helper never hits its
    /// zero-modulus guard.
    fn index(&self, item: &str, salt: usize) -> usize {
        salted_index(item, salt, SALT_MIX, self.bit_count)
    }

    /// Set the bit at index `bit` (byte `bit / 8`, offset `bit % 8`).
    fn set_bit(&mut self, bit: usize) {
        self.bits[bit / 8] |= 1u8 << (bit % 8);
    }

    /// Report whether the bit at index `bit` is set.
    fn get_bit(&self, bit: usize) -> bool {
        self.bits[bit / 8] & (1u8 << (bit % 8)) != 0
    }

    /// Add `item`: set one bit per hash function.
    ///
    /// Bits are only ever set, never cleared, so once `add(x)` runs,
    /// `contains(x)` returns `true` forever — the defining no-false-negative
    /// property of a Bloom filter.
    pub fn add(&mut self, item: &str) {
        for salt in 0..self.hashes {
            let bit = self.index(item, salt);
            self.set_bit(bit);
        }
    }

    /// Report membership of `item`: `true` iff EVERY indexed bit is set.
    ///
    /// Returns `false` on the first still-unset bit (short-circuit), so an item
    /// touching at least one unset bit is reported absent. An added item has all
    /// of its bits set, so `contains` reports it present — no false negatives.
    #[must_use]
    pub fn contains(&self, item: &str) -> bool {
        for salt in 0..self.hashes {
            let bit = self.index(item, salt);
            if !self.get_bit(bit) {
                return false;
            }
        }
        true
    }

    /// The configured number of bits (the `bit_count` constructor arg).
    #[must_use]
    pub fn bit_count(&self) -> usize {
        self.bit_count
    }

    /// The number of bytes backing the bit array = `ceil(bit_count / 8)`.
    #[must_use]
    pub fn byte_count(&self) -> usize {
        self.bits.len()
    }

    /// The configured number of hash functions.
    #[must_use]
    pub fn hash_count(&self) -> usize {
        self.hashes
    }
}

/// Python-facing compressed Bloom filter. Thin wrapper around
/// [`CompressedBloomFilterCore`] that adapts the Python boundary (exception
/// types) to the pure-Rust core.
#[pyclass]
pub struct CompressedBloomFilter {
    core: CompressedBloomFilterCore,
}

#[pymethods]
impl CompressedBloomFilter {
    /// `CompressedBloomFilter(bit_count, hashes)` — positive `bit_count`/`hashes`.
    ///
    /// Raises `ValueError("bit_count and hashes must be positive")` when either
    /// is `0`, matching the C++ kernel's surfaced exception.
    #[new]
    fn new(bit_count: usize, hashes: usize) -> PyResult<Self> {
        let core =
            CompressedBloomFilterCore::new(bit_count, hashes).map_err(PyValueError::new_err)?;
        Ok(Self { core })
    }

    /// `add(item) -> None`.
    fn add(&mut self, item: &str) {
        self.core.add(item);
    }

    /// `contains(item) -> bool`.
    fn contains(&self, item: &str) -> bool {
        self.core.contains(item)
    }

    /// `bit_count() -> int`.
    fn bit_count(&self) -> usize {
        self.core.bit_count()
    }

    /// `byte_count() -> int`.
    fn byte_count(&self) -> usize {
        self.core.byte_count()
    }

    /// `hash_count() -> int`.
    fn hash_count(&self) -> usize {
        self.core.hash_count()
    }
}

/// The Python module definition. The module name (`compressed_bloom`) MUST match
/// the `[lib] name` in `Cargo.toml` so the built artifact
/// (`compressed_bloom.so`) imports as `extensions.compressed_bloom` once it is
/// staged on `PYTHONPATH` under `extensions/`. Registering the
/// `CompressedBloomFilter` class keeps the health probe's expected attribute
/// (`CompressedBloomFilter`) present.
#[pymodule]
fn compressed_bloom(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CompressedBloomFilter>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::CompressedBloomFilterCore;

    #[test]
    fn new_rejects_zero_bit_count() {
        // Pins the guard to `bit_count == 0` (the `||`, not `&&`): zero bits
        // alone must error even with positive hashes. Kills the `|| -> &&`
        // mutant.
        assert!(CompressedBloomFilterCore::new(0, 4).is_err());
    }

    #[test]
    fn new_rejects_zero_hashes() {
        // Zero hashes alone must error even with positive bits — the other half
        // of the `||` guard. Kills `|| -> &&` from the other side.
        assert!(CompressedBloomFilterCore::new(16, 0).is_err());
    }

    #[test]
    fn new_accepts_minimum_positive_dimensions() {
        // 1 bit x 1 hash is the smallest legal filter. Kills a `== 0 -> == 1`
        // boundary mutant on the guard.
        assert!(CompressedBloomFilterCore::new(1, 1).is_ok());
    }

    #[test]
    fn accessors_echo_constructor() {
        let bloom = CompressedBloomFilterCore::new(2048, 7).unwrap();
        assert_eq!(bloom.bit_count(), 2048);
        assert_eq!(bloom.hash_count(), 7);
    }

    #[test]
    fn byte_count_is_ceil_bit_count_over_eight() {
        // Hand-computed exact values across byte boundaries: 1 bit -> 1 byte,
        // 8 bits -> 1 byte, 9 bits -> 2 bytes, 16 bits -> 2 bytes, 17 bits ->
        // 3 bytes, 1000 bits -> 125 bytes. Pins ceil division (kills a `+7`
        // -> `+0` or floor-division mutant).
        assert_eq!(
            CompressedBloomFilterCore::new(1, 1).unwrap().byte_count(),
            1
        );
        assert_eq!(
            CompressedBloomFilterCore::new(8, 1).unwrap().byte_count(),
            1
        );
        assert_eq!(
            CompressedBloomFilterCore::new(9, 1).unwrap().byte_count(),
            2
        );
        assert_eq!(
            CompressedBloomFilterCore::new(16, 1).unwrap().byte_count(),
            2
        );
        assert_eq!(
            CompressedBloomFilterCore::new(17, 1).unwrap().byte_count(),
            3
        );
        assert_eq!(
            CompressedBloomFilterCore::new(1000, 1)
                .unwrap()
                .byte_count(),
            125
        );
    }

    #[test]
    fn unseen_item_is_not_contained() {
        let bloom = CompressedBloomFilterCore::new(2048, 5).unwrap();
        assert!(!bloom.contains("never-added"));
    }

    #[test]
    fn added_item_is_contained_no_false_negative() {
        // The core Bloom guarantee: an added item is never reported absent.
        let mut bloom = CompressedBloomFilterCore::new(4096, 5).unwrap();
        bloom.add("alpha");
        assert!(bloom.contains("alpha"), "false negative after add");
    }

    #[test]
    fn no_false_negatives_for_many_added_keys() {
        // Add a batch of keys; EVERY one must be reported present (Bloom filters
        // never produce false negatives).
        let mut bloom = CompressedBloomFilterCore::new(1 << 20, 4).unwrap();
        for i in 0..5000_u64 {
            bloom.add(&format!("key-{i}"));
        }
        for i in 0..5000_u64 {
            assert!(
                bloom.contains(&format!("key-{i}")),
                "false negative for key-{i}"
            );
        }
    }

    #[test]
    fn add_is_permanent_no_remove() {
        // Unlike a counting Bloom filter, there is no remove(): a set bit stays
        // set, so a once-added item is contained forever even after many other
        // inserts.
        let mut bloom = CompressedBloomFilterCore::new(1 << 20, 4).unwrap();
        bloom.add("permanent");
        assert!(bloom.contains("permanent"));
        for i in 0..1000_u64 {
            bloom.add(&format!("noise-{i}"));
        }
        assert!(bloom.contains("permanent"), "a set bit was somehow cleared");
    }

    #[test]
    fn contains_requires_all_bits_set_not_any() {
        // A fresh filter has every bit zero, so contains() of anything must be
        // false. This kills an `all -> any` mutant on the membership check
        // (which would return true once a single bit is set).
        let fresh = CompressedBloomFilterCore::new(2048, 5).unwrap();
        assert!(!fresh.contains("anything"), "empty filter contained a key");
    }

    #[test]
    fn unicode_key_round_trips() {
        // Non-ASCII keys must hash and be found like any other (Rust strings are
        // UTF-8; the format! salting preserves the bytes).
        let mut bloom = CompressedBloomFilterCore::new(1 << 20, 4).unwrap();
        bloom.add("日本語-mañana-🚀");
        assert!(bloom.contains("日本語-mañana-🚀"));
        assert!(!bloom.contains("日本語-mañana-🛸"));
    }

    #[test]
    fn empty_string_key_is_supported() {
        let mut bloom = CompressedBloomFilterCore::new(1 << 20, 4).unwrap();
        assert!(!bloom.contains(""));
        bloom.add("");
        assert!(bloom.contains(""));
    }

    #[test]
    fn is_deterministic_across_two_filters() {
        let build = || {
            let mut bloom = CompressedBloomFilterCore::new(2048, 5).unwrap();
            for i in 0..300_u64 {
                bloom.add(&format!("d-{}", i % 40));
            }
            bloom
        };
        let a = build();
        let b = build();
        for i in 0..40_u64 {
            let key = format!("d-{i}");
            assert_eq!(
                a.contains(&key),
                b.contains(&key),
                "non-deterministic contains for {key}"
            );
        }
        assert_eq!(a.bit_count(), b.bit_count());
        assert_eq!(a.byte_count(), b.byte_count());
        assert_eq!(a.hash_count(), b.hash_count());
    }
}
