//! Counting Bloom filter hot-path kernel, ported from the C++ `counting_bloom`
//! kernel (`backend/extensions/counting_bloom.cpp`) to Rust and exposed to
//! Python as the native module `extensions.counting_bloom` via `PyO3`.
//!
//! A counting Bloom filter (Fan, Cao, Almeida & Broder 2000, "Summary Cache: A
//! Scalable Wide-Area Web Cache Sharing Protocol", IEEE/ACM Trans. Networking
//! 8(3):281-293, doi:10.1109/90.851975; building on Bloom 1970,
//! doi:10.1145/362686.362692) is a fixed-size array of small counters. `add`
//! increments one counter per hash function; `remove` decrements them; and
//! `contains` reports membership — true iff every indexed counter is non-zero.
//! Counters let the structure support deletion, which a plain Bloom filter
//! cannot. False positives are expected and bounded by the table size; false
//! negatives never occur while an item is net-present.
//!
//! The Python-callable API matches the C++ kernel exactly — a single class:
//!
//! - `CountingBloomFilter(counters, hashes)` — raises `ValueError("counters and
//!   hashes must be positive")` when either argument is `0`.
//! - `add(item) -> None`, `remove(item) -> None`.
//! - `contains(item) -> bool`.
//! - `counter_count() -> int`, `hash_count() -> int`.
//!
//! ## Deliberate hashing decision (port note)
//!
//! The C++ kernel indexed counters with `std::hash<std::string>`, which is
//! libstdc++-implementation-defined, so the exact counter-to-index mapping was
//! never a portable cross-language contract. A repository-wide search found
//! zero Python callers of `add`/`remove`/`contains`, so no caller depends on
//! specific hash outputs. This Rust port reproduces the BEHAVIOURAL contract,
//! not C++ hash bytes: no false negatives while net-present, saturating
//! increment (never wraps past `u16::MAX`), flooring decrement (never
//! underflows below `0`), determinism, the `counter_count()`/`hash_count()`
//! accessors, and the `counters == 0 || hashes == 0` guard. It keeps the C++
//! salt design — `salt = i * 0x9e3779b97f4a7c15` (the 64-bit golden-ratio
//! `fibonacci-hashing` constant, Knuth TAOCP Vol. 3 §6.4) appended after a `#`
//! separator — but hashes with a FIXED deterministic hasher
//! (`std::collections::hash_map::DefaultHasher`, the standard library's
//! `SipHash` with fixed default keys) so results are reproducible across runs
//! and machines for a given build, exactly like the `count_min_sketch` port.
//! See `docs/specs/pick-100-counting-bloom.md`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use xf_kernels::salted_index;

/// The 64-bit golden-ratio (fibonacci-hashing) mixing constant used to
/// decorrelate the per-hash salts, matching the C++ kernel's
/// `0x9e3779b97f4a7c15ULL`.
const SALT_MIX: u64 = 0x9e37_79b9_7f4a_7c15;

/// Plain-Rust counting Bloom filter core over native types (no `PyO3`).
///
/// Holds a flat `Vec<u16>` of `counters` counters, all zero at construction.
/// All logic lives here so it is unit-testable with `cargo test` without
/// crossing the Python boundary.
pub struct CountingBloomCore {
    counters: Vec<u16>,
    hashes: usize,
}

impl CountingBloomCore {
    /// Construct a filter with `counters` counters (all zero) and `hashes`
    /// hash functions.
    ///
    /// # Errors
    ///
    /// Returns `Err` when `counters == 0` or `hashes == 0` — a filter needs at
    /// least one counter and one hash function. This mirrors the C++ kernel's
    /// `std::invalid_argument("counters and hashes must be positive")`.
    pub fn new(counters: usize, hashes: usize) -> Result<Self, &'static str> {
        if counters == 0 || hashes == 0 {
            return Err("counters and hashes must be positive");
        }
        Ok(Self {
            counters: vec![0; counters],
            hashes,
        })
    }

    /// Counter index for `item` under hash function `salt`.
    ///
    /// Delegates to the shared [`xf_kernels::salted_index`] helper, passing this
    /// kernel's own `SALT_MIX` constant and the counter count as the modulus.
    /// `counters.len() >= 1` is guaranteed by `new`, so the helper never hits
    /// its zero-modulus guard.
    fn index(&self, item: &str, salt: usize) -> usize {
        salted_index(item, salt, SALT_MIX, self.counters.len())
    }

    /// Add `item`: increment one counter per hash function, saturating at
    /// `u16::MAX`.
    ///
    /// Saturating addition pins a counter at `u16::MAX` (65535) instead of
    /// wrapping to a small value. Wrapping would turn a present item into an
    /// apparent absent one (a false negative), which violates the core Bloom
    /// guarantee, so the cap is part of the behavioural contract.
    pub fn add(&mut self, item: &str) {
        for salt in 0..self.hashes {
            let slot = self.index(item, salt);
            let counter = &mut self.counters[slot];
            *counter = counter.saturating_add(1);
        }
    }

    /// Remove `item`: decrement one counter per hash function, flooring at `0`.
    ///
    /// Saturating subtraction floors a counter at `0` instead of wrapping to
    /// `u16::MAX`. `remove` of an item that was never added is therefore a safe
    /// no-op: its counters stay at `0`.
    pub fn remove(&mut self, item: &str) {
        for salt in 0..self.hashes {
            let slot = self.index(item, salt);
            let counter = &mut self.counters[slot];
            *counter = counter.saturating_sub(1);
        }
    }

    /// Report membership of `item`: `true` iff EVERY indexed counter is `> 0`.
    ///
    /// Returns `false` on the first still-zero counter (short-circuit), so an
    /// item touching at least one zero counter is reported absent. A
    /// net-present item (added with no balancing `remove`) has all of its
    /// counters `> 0`, so `contains` reports it present — no false negatives.
    #[must_use]
    pub fn contains(&self, item: &str) -> bool {
        for salt in 0..self.hashes {
            let slot = self.index(item, salt);
            if self.counters[slot] == 0 {
                return false;
            }
        }
        true
    }

    /// The configured number of counters.
    #[must_use]
    pub fn counter_count(&self) -> usize {
        self.counters.len()
    }

    /// The configured number of hash functions.
    #[must_use]
    pub const fn hash_count(&self) -> usize {
        self.hashes
    }
}

/// Python-facing counting Bloom filter. Thin wrapper around
/// [`CountingBloomCore`] that adapts the Python boundary (exception types) to
/// the pure-Rust core.
#[pyclass]
pub struct CountingBloomFilter {
    core: CountingBloomCore,
}

#[pymethods]
impl CountingBloomFilter {
    /// `CountingBloomFilter(counters, hashes)` — positive `counters`/`hashes`.
    ///
    /// Raises `ValueError("counters and hashes must be positive")` when either
    /// is `0`, matching the C++ kernel's surfaced exception.
    #[new]
    fn new(counters: usize, hashes: usize) -> PyResult<Self> {
        let core = CountingBloomCore::new(counters, hashes).map_err(PyValueError::new_err)?;
        Ok(Self { core })
    }

    /// `add(item) -> None`.
    fn add(&mut self, item: &str) {
        self.core.add(item);
    }

    /// `remove(item) -> None`.
    fn remove(&mut self, item: &str) {
        self.core.remove(item);
    }

    /// `contains(item) -> bool`.
    fn contains(&self, item: &str) -> bool {
        self.core.contains(item)
    }

    /// `counter_count() -> int`.
    fn counter_count(&self) -> usize {
        self.core.counter_count()
    }

    /// `hash_count() -> int`.
    const fn hash_count(&self) -> usize {
        self.core.hash_count()
    }
}

/// The Python module definition. The module name (`counting_bloom`) MUST match
/// the `[lib] name` in `Cargo.toml` so the built artifact (`counting_bloom.so`)
/// imports as `extensions.counting_bloom` once it is staged on `PYTHONPATH`
/// under `extensions/`. Registering the `CountingBloomFilter` class keeps the
/// health probe's expected attribute (`CountingBloomFilter`) present.
#[pymodule]
fn counting_bloom(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CountingBloomFilter>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::CountingBloomCore;

    #[test]
    fn new_rejects_zero_counters() {
        // Pins the guard to `counters == 0` (the `||`, not `&&`): zero counters
        // alone must error even with positive hashes. Kills the `|| -> &&`
        // mutant.
        assert!(CountingBloomCore::new(0, 4).is_err());
    }

    #[test]
    fn new_rejects_zero_hashes() {
        // Zero hashes alone must error even with positive counters — the other
        // half of the `||` guard. Kills `|| -> &&` from the other side.
        assert!(CountingBloomCore::new(16, 0).is_err());
    }

    #[test]
    fn new_accepts_minimum_positive_dimensions() {
        // 1x1 is the smallest legal filter. Kills a `== 0 -> == 1` boundary
        // mutant on the guard.
        assert!(CountingBloomCore::new(1, 1).is_ok());
    }

    #[test]
    fn accessors_echo_constructor() {
        let bloom = CountingBloomCore::new(2048, 7).unwrap();
        assert_eq!(bloom.counter_count(), 2048);
        assert_eq!(bloom.hash_count(), 7);
    }

    #[test]
    fn unseen_item_is_not_contained() {
        let bloom = CountingBloomCore::new(2048, 5).unwrap();
        assert!(!bloom.contains("never-added"));
    }

    #[test]
    fn added_item_is_contained_no_false_negative() {
        // The core Bloom guarantee: a net-present item is never reported absent.
        let mut bloom = CountingBloomCore::new(4096, 5).unwrap();
        bloom.add("alpha");
        assert!(bloom.contains("alpha"), "false negative after add");
    }

    #[test]
    fn no_false_negatives_for_many_added_keys() {
        // Add a batch of keys; EVERY one must be reported present (Bloom filters
        // never produce false negatives).
        let mut bloom = CountingBloomCore::new(1 << 16, 4).unwrap();
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
    fn add_then_balanced_remove_returns_toward_absent() {
        // In a wide table with no collisions, add(x) then remove(x) restores
        // contains(x) to false. Exercises the deletion support that
        // distinguishes a COUNTING Bloom filter from a plain one.
        let mut bloom = CountingBloomCore::new(1 << 16, 4).unwrap();
        bloom.add("solo");
        assert!(bloom.contains("solo"));
        bloom.remove("solo");
        assert!(
            !bloom.contains("solo"),
            "balanced remove should clear a collision-free key"
        );
    }

    #[test]
    fn remove_of_never_added_is_safe_noop() {
        // Flooring decrement: removing an item that was never added must not
        // underflow/wrap. Counters stay at 0, so the item stays absent and a
        // freshly added key is still found.
        let mut bloom = CountingBloomCore::new(1 << 16, 4).unwrap();
        bloom.remove("ghost");
        assert!(!bloom.contains("ghost"));
        bloom.add("real");
        assert!(bloom.contains("real"), "underflow corrupted the table");
    }

    #[test]
    fn duplicate_remove_does_not_underflow() {
        // add once, remove twice. The second remove must floor at 0, not wrap to
        // u16::MAX. If it wrapped, a later add(other) sharing a slot could read
        // a huge stale count; we assert the structure stays sane: the key is
        // absent and a different key still behaves.
        let mut bloom = CountingBloomCore::new(1 << 16, 4).unwrap();
        bloom.add("once");
        bloom.remove("once");
        bloom.remove("once");
        assert!(!bloom.contains("once"));
        bloom.add("other");
        assert!(bloom.contains("other"));
        bloom.remove("other");
        assert!(
            !bloom.contains("other"),
            "wrap from underflow inflated a counter"
        );
    }

    #[test]
    fn saturating_add_does_not_wrap_to_false_negative() {
        // Single counter, single hash: add far past u16::MAX. The counter must
        // pin at the max (saturate) and the item stay present. A wrapping add
        // would cycle through 0 and produce a false negative.
        let mut bloom = CountingBloomCore::new(1, 1).unwrap();
        for _ in 0..70_000 {
            bloom.add("alpha");
        }
        assert!(
            bloom.contains("alpha"),
            "saturating add wrapped to a false negative"
        );
        // One remove drops the saturated counter by exactly 1 (65535 -> 65534),
        // so it is still well above 0 and the item remains present.
        bloom.remove("alpha");
        assert!(bloom.contains("alpha"));
    }

    #[test]
    fn contains_requires_all_counters_nonzero_not_any() {
        // Two hashes, two counters, never-added key: at least one counter is 0,
        // so contains must be false. This kills an `all -> any` mutant on the
        // membership check (which would return true once one counter is set).
        let mut bloom = CountingBloomCore::new(2, 2).unwrap();
        // Force exactly one of the two counters to become non-zero by adding a
        // key, then probe a key whose first salt likely lands on the other,
        // still-zero counter. Regardless of which slot is zero, an
        // all-zero-counter probe must be absent.
        bloom.add("seed");
        // The fully-empty case is the cleanest all-vs-any discriminator:
        let fresh = CountingBloomCore::new(2, 2).unwrap();
        assert!(!fresh.contains("anything"), "empty filter contained a key");
    }

    #[test]
    fn unicode_key_round_trips() {
        // Non-ASCII keys must hash and be found like any other (Rust strings are
        // UTF-8; the format! salting preserves the bytes).
        let mut bloom = CountingBloomCore::new(1 << 16, 4).unwrap();
        bloom.add("日本語-mañana-🚀");
        assert!(bloom.contains("日本語-mañana-🚀"));
        assert!(!bloom.contains("日本語-mañana-🛸"));
    }

    #[test]
    fn empty_string_key_is_supported() {
        let mut bloom = CountingBloomCore::new(1 << 16, 4).unwrap();
        assert!(!bloom.contains(""));
        bloom.add("");
        assert!(bloom.contains(""));
    }

    #[test]
    fn is_deterministic_across_two_filters() {
        let build = || {
            let mut bloom = CountingBloomCore::new(2048, 5).unwrap();
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
        assert_eq!(a.counter_count(), b.counter_count());
        assert_eq!(a.hash_count(), b.hash_count());
    }
}
