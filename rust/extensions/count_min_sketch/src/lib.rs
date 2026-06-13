//! Count-Min Sketch hot-path kernel, ported from the C++ `count_min_sketch`
//! kernel (`backend/extensions/count_min_sketch.cpp`) to Rust and exposed to
//! Python as the native module `extensions.count_min_sketch` via `PyO3`.
//!
//! A Count-Min Sketch (Cormode & Muthukrishnan 2005, "An Improved Data Stream
//! Summary: The Count-Min Sketch and its Applications", J. Algorithms 55(1),
//! doi:10.1016/j.jalgor.2003.12.001) is a `depth`-row by `width`-column table
//! of unsigned counters. `add` increments one counter per row; `estimate`
//! returns the minimum counter across the rows, which is a one-sided
//! over-estimate of the true count (it never undercounts).
//!
//! The Python-callable API matches the C++ kernel exactly — a single class:
//!
//! - `CountMinSketch(width, depth)` — raises `ValueError("width and depth must
//!   be positive")` when either argument is `0`.
//! - `add(item, count=1) -> None`.
//! - `estimate(item) -> int` — the minimum counter across rows.
//! - `width() -> int`, `depth() -> int`.
//!
//! ## Deliberate hashing decision (port note)
//!
//! The C++ kernel indexed rows with `std::hash<std::string>`, which is
//! libstdc++-implementation-defined, so the exact counter VALUES were never a
//! portable cross-language contract. A repository-wide search found zero Python
//! callers of `add`/`estimate`, so no caller depends on specific hash outputs.
//! This Rust port reproduces the BEHAVIOURAL contract, not C++ hash bytes:
//! deterministic, depth independent-ish rows via the same salt-mixing scheme,
//! `estimate = min` over rows, `estimate >= true count` always, monotonic under
//! `add`, the `width()`/`depth()` accessors, and the `width == 0 || depth == 0`
//! guard. It keeps the C++ row-salt design — `salt = row * 0x94d049bb133111eb`
//! (the `SplitMix64`/fmix mixing constant, Steele/Lea/Flood 2014,
//! doi:10.1145/2660193.2660195) — but hashes with a FIXED deterministic hasher
//! (`std::collections::hash_map::DefaultHasher`, the standard library's
//! `SipHash` with fixed default keys) so estimates are reproducible. See
//! `docs/specs/pick-97-count-min-sketch.md`.

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use xf_kernels::salted_index;

/// The `SplitMix64`/fmix mixing constant used to decorrelate the per-row salts,
/// matching the C++ kernel's `0x94d049bb133111ebULL`.
const SALT_MIX: u64 = 0x94d0_49bb_1331_11eb;

/// Plain-Rust Count-Min Sketch core over native types (no `PyO3`).
///
/// Holds a flat `width * depth` table of `u64` counters in row-major order, so
/// the counter for row `r` at column `c` lives at `table[r * width + c]`. All
/// logic lives here so it is unit-testable with `cargo test` without crossing
/// the Python boundary.
pub struct CountMinSketchCore {
    table: Vec<u64>,
    width: usize,
    depth: usize,
}

impl CountMinSketchCore {
    /// Construct a `width`-by-`depth` sketch with all counters zero.
    ///
    /// # Errors
    ///
    /// Returns `Err` when `width == 0` or `depth == 0` — a sketch needs at
    /// least one column and one row. This mirrors the C++ kernel's
    /// `std::invalid_argument("width and depth must be positive")`.
    pub fn new(width: usize, depth: usize) -> Result<Self, &'static str> {
        if width == 0 || depth == 0 {
            return Err("width and depth must be positive");
        }
        Ok(Self {
            table: vec![0; width * depth],
            width,
            depth,
        })
    }

    /// Column index for `item` in the given `row`.
    ///
    /// Delegates to the shared [`xf_kernels::salted_index`] helper, passing this
    /// kernel's own `SALT_MIX` constant and `width` as the modulus. `width >= 1`
    /// is guaranteed by `new`, so the helper never hits its zero-modulus guard.
    fn index(&self, item: &str, row: usize) -> usize {
        salted_index(item, row, SALT_MIX, self.width)
    }

    /// Add `count` occurrences of `item`: increment one counter per row.
    ///
    /// Uses saturating addition so a pathological overflow at `u64::MAX`
    /// pins the counter at the maximum instead of wrapping to a small value,
    /// which would otherwise violate the no-undercount guarantee.
    pub fn add(&mut self, item: &str, count: u64) {
        for row in 0..self.depth {
            let col = self.index(item, row);
            let cell = &mut self.table[row * self.width + col];
            *cell = cell.saturating_add(count);
        }
    }

    /// Estimate the count of `item`: the MINIMUM counter across all rows.
    ///
    /// The minimum is the Count-Min over-estimate (Cormode & Muthukrishnan
    /// 2005): every row's counter is `>=` the true count, so their minimum is
    /// the tightest over-estimate and never undercounts. An unseen item maps to
    /// at least one still-zero counter (modulo collisions), so its estimate is
    /// `0` for an empty or never-touched key.
    #[must_use]
    pub fn estimate(&self, item: &str) -> u64 {
        let mut best = u64::MAX;
        for row in 0..self.depth {
            let col = self.index(item, row);
            best = best.min(self.table[row * self.width + col]);
        }
        best
    }

    /// The configured number of columns.
    #[must_use]
    pub const fn width(&self) -> usize {
        self.width
    }

    /// The configured number of rows (independent hash functions).
    #[must_use]
    pub const fn depth(&self) -> usize {
        self.depth
    }
}

/// Python-facing Count-Min Sketch. Thin wrapper around [`CountMinSketchCore`]
/// that adapts the Python boundary (exception types, default `count`) to the
/// pure-Rust core.
#[pyclass]
pub struct CountMinSketch {
    core: CountMinSketchCore,
}

#[pymethods]
impl CountMinSketch {
    /// `CountMinSketch(width, depth)` — positive `width`/`depth`.
    ///
    /// Raises `ValueError("width and depth must be positive")` when either is
    /// `0`, matching the C++ kernel's surfaced exception.
    #[new]
    fn new(width: usize, depth: usize) -> PyResult<Self> {
        let core = CountMinSketchCore::new(width, depth).map_err(PyValueError::new_err)?;
        Ok(Self { core })
    }

    /// `add(item, count=1) -> None`.
    #[pyo3(signature = (item, count=1))]
    fn add(&mut self, item: &str, count: u64) {
        self.core.add(item, count);
    }

    /// `estimate(item) -> int` — minimum counter across rows.
    fn estimate(&self, item: &str) -> u64 {
        self.core.estimate(item)
    }

    /// `width() -> int`.
    const fn width(&self) -> usize {
        self.core.width()
    }

    /// `depth() -> int`.
    const fn depth(&self) -> usize {
        self.core.depth()
    }
}

/// The Python module definition. The module name (`count_min_sketch`) MUST
/// match the `[lib] name` in `Cargo.toml` so the built artifact
/// (`count_min_sketch.so`) imports as `extensions.count_min_sketch` once it is
/// staged on `PYTHONPATH` under `extensions/`. Registering the `CountMinSketch`
/// class keeps the health probe's expected attribute (`CountMinSketch`)
/// present.
#[pymodule]
fn count_min_sketch(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CountMinSketch>()?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::CountMinSketchCore;

    #[test]
    fn new_rejects_zero_width() {
        // Pins the guard to `width == 0` (not `< 0`, impossible for usize, and
        // the `||` not `&&`): a zero width alone must error even with positive
        // depth. Kills the `|| -> &&` mutant.
        assert!(CountMinSketchCore::new(0, 5).is_err());
    }

    #[test]
    fn new_rejects_zero_depth() {
        // Zero depth alone must error even with positive width — the other half
        // of the `||` guard. Kills the `|| -> &&` mutant from the other side.
        assert!(CountMinSketchCore::new(16, 0).is_err());
    }

    #[test]
    fn new_accepts_minimum_positive_dimensions() {
        // 1x1 is the smallest legal sketch. Kills a `== 0 -> == 1` /
        // `>= 1 -> > 1` boundary mutant on the guard.
        assert!(CountMinSketchCore::new(1, 1).is_ok());
    }

    #[test]
    fn unseen_item_estimates_zero() {
        let cms = CountMinSketchCore::new(2048, 5).unwrap();
        assert_eq!(cms.estimate("never-added"), 0);
    }

    #[test]
    fn estimate_never_undercounts_single_key() {
        // The core Count-Min guarantee (Cormode & Muthukrishnan 2005).
        let mut cms = CountMinSketchCore::new(4096, 5).unwrap();
        cms.add("alpha", 7);
        assert!(cms.estimate("alpha") >= 7, "estimate undercounted");
    }

    #[test]
    fn estimate_is_exact_for_heavy_hitter_with_wide_table() {
        // With a generous width/depth the collision probability is tiny, so a
        // single key's estimate equals its true count exactly.
        let mut cms = CountMinSketchCore::new(65_536, 7).unwrap();
        for _ in 0..1000 {
            cms.add("hot", 1);
        }
        assert_eq!(cms.estimate("hot"), 1000);
    }

    #[test]
    fn estimate_never_undercounts_many_keys() {
        let mut cms = CountMinSketchCore::new(1024, 4).unwrap();
        let mut truth = std::collections::HashMap::new();
        for i in 0..5000_u64 {
            let key = format!("key-{}", i % 250);
            let inc = (i % 3) + 1;
            cms.add(&key, inc);
            *truth.entry(key).or_insert(0_u64) += inc;
        }
        for (key, &true_count) in &truth {
            assert!(
                cms.estimate(key) >= true_count,
                "estimate {} undercounted true {} for {key}",
                cms.estimate(key),
                true_count
            );
        }
    }

    #[test]
    fn add_default_count_is_one() {
        let mut cms = CountMinSketchCore::new(8192, 5).unwrap();
        cms.add("solo", 1);
        // Wide table -> no collision -> exact.
        assert_eq!(cms.estimate("solo"), 1);
    }

    #[test]
    fn estimate_is_monotonic_non_decreasing() {
        let mut cms = CountMinSketchCore::new(8192, 5).unwrap();
        let mut prev = 0_u64;
        for _ in 0..50 {
            cms.add("grow", 1);
            let now = cms.estimate("grow");
            assert!(now >= prev, "estimate fell from {prev} to {now}");
            prev = now;
        }
    }

    #[test]
    fn estimate_is_deterministic_across_two_sketches() {
        let build = || {
            let mut cms = CountMinSketchCore::new(2048, 5).unwrap();
            for i in 0..300_u64 {
                cms.add(&format!("d-{}", i % 40), 2);
            }
            cms
        };
        let a = build();
        let b = build();
        for i in 0..40_u64 {
            let key = format!("d-{i}");
            assert_eq!(a.estimate(&key), b.estimate(&key));
        }
    }

    #[test]
    fn estimate_returns_min_not_max_or_sum() {
        // Force the rows of one key to hold DIFFERENT counts by colliding only
        // some rows with other keys, then assert the estimate equals the
        // smallest row counter — not the largest and not the sum. This kills a
        // `min -> max` and a `min -> +=`(sum) mutant on `estimate`.
        let mut cms = CountMinSketchCore::new(64, 6).unwrap();
        // Add the target once: every one of its row counters is now >= 1.
        cms.add("target", 1);
        let base = cms.estimate("target");
        assert_eq!(
            base, 1,
            "fresh single add should estimate 1 in a 64-wide table"
        );

        // Hammer many other keys so collisions inflate SOME of target's rows
        // above 1, leaving at least one row still at 1. The MIN must stay 1;
        // a max/sum would jump well above 1.
        for i in 0..10_000_u64 {
            cms.add(&format!("noise-{i}"), 1);
        }
        let est = cms.estimate("target");
        assert!(
            est >= 1,
            "min estimate must never undercount the true count of 1"
        );
        // The true count is 1. With min-over-rows and a 64-wide / 6-deep table,
        // at least one of target's six rows is overwhelmingly likely to remain
        // uncollided-low; a max/sum aggregation would instead report a large
        // inflated number. We assert the estimate stays modest (min behaviour),
        // not the large value a sum would give.
        let summed_floor = 10_000_u64 / 64; // rough per-cell load
        assert!(
            est < summed_floor,
            "estimate {est} looks like a max/sum, not a min (load floor {summed_floor})"
        );
    }
}
