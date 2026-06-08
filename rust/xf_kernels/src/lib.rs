//! Shared Rust helpers reused across the hot-path kernel crates.
//!
//! This crate holds small, pure functions that more than one kernel needs, so
//! the logic lives in exactly one place (DRY) instead of being copy-pasted into
//! each crate. Today it exposes one helper:
//!
//! - [`salted_index`] — the deterministic salted hash index shared by the
//!   streaming-sketch and Bloom-filter kernels (`count_min_sketch`,
//!   `counting_bloom`, `compressed_bloom`).
//!
//! Each caller keeps its own mixing constant (`salt_mix`) and its own modulus,
//! so the *shape* of the hash is shared but every kernel stays independent.
//!
//! The crate also still builds as a `PyO3` extension module to prove the
//! Rust -> `PyO3` -> `maturin` -> Python build path end to end; it exposes a
//! single [`version`] function for that smoke check. The compute helpers are
//! plain Rust over native types so `cargo test` can exercise them without
//! crossing the Python boundary.

use std::collections::hash_map::DefaultHasher;
use std::hash::{Hash, Hasher};

use pyo3::prelude::*;

/// Deterministic salted hash index shared by the sketch / Bloom kernels.
///
/// Mirrors the original C++ `index`: salt the key with the per-hash-function
/// `salt` multiplied by the caller's `salt_mix` mixing constant, append it
/// after a `#` separator, hash the concatenation with a fixed deterministic
/// hasher (`DefaultHasher`), and reduce modulo `modulus`. A fresh hasher per
/// call keeps the result a pure function of `(item, salt, salt_mix, modulus)`,
/// so callers are deterministic across calls and across runs.
///
/// The `salt_mix` is supplied by the caller (each kernel keeps its own constant
/// — e.g. `count_min_sketch` uses `0x94d0_49bb_1331_11eb`,
/// `counting_bloom` uses `0x9e37_79b9_7f4a_7c15`,
/// `compressed_bloom` uses `0x517c_c1b7_2722_0a95`), so the shared shape never
/// forces two kernels to collide on the same salt schedule.
///
/// # Panics
///
/// Panics if `modulus == 0` (a divide-by-zero). Every caller guarantees a
/// non-zero modulus at construction time, so this never fires in practice; the
/// explicit check documents the precondition instead of leaving an opaque
/// arithmetic panic.
#[must_use]
pub fn salted_index(item: &str, salt: usize, salt_mix: u64, modulus: usize) -> usize {
    assert!(modulus != 0, "salted_index requires a non-zero modulus");
    let mixed = format!("{item}#{}", (salt as u64).wrapping_mul(salt_mix));
    let mut hasher = DefaultHasher::new();
    mixed.hash(&mut hasher);
    // `modulus >= 1`, so the remainder is strictly less than `modulus` (a
    // `usize`), which makes the `u64 -> usize` conversion always lossless.
    // `try_from(...).expect` documents that and satisfies clippy's
    // `cast_possible_truncation` lint.
    let slot = hasher.finish() % modulus as u64;
    usize::try_from(slot).expect("remainder is < modulus, which is a usize")
}

/// Return the crate version (compile-time `CARGO_PKG_VERSION`).
#[pyfunction]
const fn version() -> &'static str {
    env!("CARGO_PKG_VERSION")
}

/// The Python module definition. The module name (`xf_kernels`) must match the
/// `[lib] name` in `Cargo.toml` and the `[project] name` in `pyproject.toml`,
/// otherwise the import name and the built artifact name disagree.
#[pymodule]
fn xf_kernels(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(version, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::salted_index;

    // Mixing constants the three real kernels use, copied here so the tests
    // exercise the exact salt schedules the callers pass in.
    const CMS_MIX: u64 = 0x94d0_49bb_1331_11eb;
    const COUNTING_MIX: u64 = 0x9e37_79b9_7f4a_7c15;
    const COMPRESSED_MIX: u64 = 0x517c_c1b7_2722_0a95;

    #[test]
    fn index_is_always_within_modulus() {
        for modulus in [1usize, 2, 7, 64, 1000] {
            for salt in 0..8usize {
                let i = salted_index("hello", salt, CMS_MIX, modulus);
                assert!(i < modulus, "index {i} must be < modulus {modulus}");
            }
        }
    }

    #[test]
    fn index_is_deterministic_across_calls() {
        let a = salted_index("link-target", 3, COUNTING_MIX, 4096);
        let b = salted_index("link-target", 3, COUNTING_MIX, 4096);
        assert_eq!(a, b, "same inputs must give the same index");
    }

    #[test]
    fn different_salts_decorrelate_rows() {
        // The whole point of the salt schedule: different hash-function rows
        // should (almost always) land in different slots for the same key.
        let row0 = salted_index("anchor", 0, CMS_MIX, 1_000_000);
        let row1 = salted_index("anchor", 1, CMS_MIX, 1_000_000);
        let row2 = salted_index("anchor", 2, CMS_MIX, 1_000_000);
        assert!(
            row0 != row1 || row1 != row2,
            "consecutive salted rows should not all collide"
        );
    }

    #[test]
    fn different_mixing_constants_change_the_schedule() {
        // Two kernels with different mixing constants must not be forced into
        // the same index for a non-zero salt, otherwise lifting the shared
        // helper would have silently merged their salt schedules.
        let counting = salted_index("token", 1, COUNTING_MIX, 1_000_000);
        let compressed = salted_index("token", 1, COMPRESSED_MIX, 1_000_000);
        assert_ne!(
            counting, compressed,
            "distinct mixing constants must produce distinct schedules at salt=1"
        );
    }

    #[test]
    fn modulus_one_collapses_to_zero() {
        // Boundary: a single-slot table must always return slot 0, never panic.
        for salt in 0..5usize {
            assert_eq!(salted_index("x", salt, CMS_MIX, 1), 0);
        }
    }

    #[test]
    #[should_panic(expected = "non-zero modulus")]
    fn zero_modulus_panics() {
        let _ = salted_index("x", 0, CMS_MIX, 0);
    }
}
