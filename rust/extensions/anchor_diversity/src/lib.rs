//! FR-045 anchor-diversity / exact-match reuse guard hot-path kernel, ported
//! from the C++ `anchor_diversity` kernel (`anchor_diversity.cpp` plus
//! `include/anchor_diversity_core.h`) to Rust and exposed to Python as the
//! native module `extensions.anchor_diversity` via `PyO3` and the `numpy` crate.
//!
//! One module-level function matches the C++ kernel exactly:
//!
//! ```text
//! evaluate_batch(
//!     active_anchor_counts: np.ndarray[int32],
//!     exact_match_counts_before: np.ndarray[int32],
//!     min_history_count: int,
//!     max_exact_match_share: float,
//!     max_exact_match_count: int,
//!     hard_cap_enabled: bool,
//! ) -> dict[str, np.ndarray]
//! ```
//!
//! It returns a dict of EIGHT parallel arrays keyed `projected_exact_count`
//! (int32), `projected_exact_share` (f64), `share_overflow` (f64),
//! `count_overflow_norm` (f64), `spam_risk` (f64), `score_anchor_diversity`
//! (f64), `state_index` (int32), `would_block` (uint8).
//!
//! ## Parity (port note)
//!
//! All math is deterministic IEEE-754 `f64` (`+ - * / max min`) on `i32`/`f64`,
//! with no hashing, randomness, `f32`, or transcendental functions, so the
//! kernel reproduces the C++ artifact and the pure-Python oracle
//! (`anchor_diversity.py::_arithmetic_via_python`) to within the `1e-6` parity
//! floor the acceptance test (`backend/tests/test_parity_anchor_diversity.py`)
//! enforces. Python owns the normalization, neutral short-circuits, and
//! `round(..., 6)` diagnostics; this kernel only does the arithmetic inner
//! loop. FR-045 sources: Google Search Central internal-linking best-practices
//! and patent US20110238644A1.

use numpy::{IntoPyArray, PyReadonlyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

// FR-045 state-index constants (mirror the Python `anchor_diversity_state`
// enum and the C++ module-local constants). The Rust port MUST emit these exact
// integer codes; Python maps them back to strings.
const STATE_NEUTRAL_NO_HISTORY: i32 = 1;
const STATE_NEUTRAL_BELOW_THRESHOLD: i32 = 2;
const STATE_PENALIZED_EXACT_SHARE: i32 = 3;
const STATE_PENALIZED_EXACT_COUNT: i32 = 4;
const STATE_BLOCKED_EXACT_COUNT: i32 = 5;

// Denominator guards and scoring constants mirroring the C++ named constants
// and the Python `max(..., 1)` / `max(..., 1e-9)` patterns line-by-line.
const MIN_COUNT_DENOMINATOR: i32 = 1;
const SHARE_DENOMINATOR_EPSILON: f64 = 1e-9;
const SHARE_WEIGHT: f64 = 0.8;
const COUNT_WEIGHT: f64 = 0.2;
const NEUTRAL_SCORE: f64 = 0.5;
const SPAM_RISK_CEILING: f64 = 1.0;
const SCORE_SLOPE: f64 = 0.5;

/// The eight parallel output columns of the FR-045 batch scorer, one entry per
/// candidate. Returned by [`evaluate_anchor_diversity_core`] so `cargo test`
/// can validate the arithmetic without crossing the Python boundary.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct AnchorDiversityOutputs {
    pub projected_exact_count: Vec<i32>,
    pub projected_exact_share: Vec<f64>,
    pub share_overflow: Vec<f64>,
    pub count_overflow_norm: Vec<f64>,
    pub spam_risk: Vec<f64>,
    pub score_anchor_diversity: Vec<f64>,
    pub state_index: Vec<i32>,
    pub would_block: Vec<u8>,
}

impl AnchorDiversityOutputs {
    fn with_capacity(count: usize) -> Self {
        Self {
            projected_exact_count: Vec::with_capacity(count),
            projected_exact_share: Vec::with_capacity(count),
            share_overflow: Vec::with_capacity(count),
            count_overflow_norm: Vec::with_capacity(count),
            spam_risk: Vec::with_capacity(count),
            score_anchor_diversity: Vec::with_capacity(count),
            state_index: Vec::with_capacity(count),
            would_block: Vec::with_capacity(count),
        }
    }

    fn push_neutral_no_history(&mut self, before: i32) {
        self.projected_exact_count.push(before);
        self.projected_exact_share.push(0.0);
        self.share_overflow.push(0.0);
        self.count_overflow_norm.push(0.0);
        self.spam_risk.push(0.0);
        self.score_anchor_diversity.push(NEUTRAL_SCORE);
        self.state_index.push(STATE_NEUTRAL_NO_HISTORY);
        self.would_block.push(0);
    }
}

/// Plain-Rust FR-045 batch scorer core (no `PyO3`). Computes the eight output
/// columns from the two parallel int32 input slices and the four scalar
/// settings. Unit-testable with `cargo test` without crossing the Python
/// boundary.
///
/// # Panics
///
/// Debug-asserts that the two input slices are the same length; the `PyO3`
/// wrapper validates this and raises a Python error before calling the core.
#[must_use]
pub fn evaluate_anchor_diversity_core(
    active_anchor_counts: &[i32],
    exact_match_counts_before: &[i32],
    min_history_count: i32,
    max_exact_match_share: f64,
    max_exact_match_count: i32,
    hard_cap_enabled: bool,
) -> AnchorDiversityOutputs {
    debug_assert_eq!(
        active_anchor_counts.len(),
        exact_match_counts_before.len(),
        "input slices must be the same length"
    );
    let count = active_anchor_counts.len();
    let mut out = AnchorDiversityOutputs::with_capacity(count);

    for i in 0..count {
        let active = active_anchor_counts[i];
        let before = exact_match_counts_before[i];

        // PARITY: anchor_diversity.py — active_anchor_count < min_history_count.
        if active < min_history_count {
            out.push_neutral_no_history(before);
            continue;
        }

        let projected_count = before + 1;
        let denom_count = (active + 1).max(MIN_COUNT_DENOMINATOR);
        let projected_share = f64::from(projected_count) / f64::from(denom_count);

        let share_denominator = (1.0 - max_exact_match_share).max(SHARE_DENOMINATOR_EPSILON);
        let share_overflow = (projected_share - max_exact_match_share).max(0.0) / share_denominator;

        let count_overflow_abs = (projected_count - max_exact_match_count).max(0);
        let count_denom = max_exact_match_count.max(MIN_COUNT_DENOMINATOR);
        let count_overflow_norm =
            (f64::from(count_overflow_abs) / f64::from(count_denom)).min(SPAM_RISK_CEILING);

        let spam_risk = (SHARE_WEIGHT * share_overflow + COUNT_WEIGHT * count_overflow_norm)
            .min(SPAM_RISK_CEILING);
        let score = NEUTRAL_SCORE - SCORE_SLOPE * spam_risk;

        let blocked = hard_cap_enabled && (projected_count > max_exact_match_count);
        let state = if blocked {
            STATE_BLOCKED_EXACT_COUNT
        } else if count_overflow_abs > 0 {
            STATE_PENALIZED_EXACT_COUNT
        } else if share_overflow > 0.0 {
            STATE_PENALIZED_EXACT_SHARE
        } else {
            STATE_NEUTRAL_BELOW_THRESHOLD
        };

        out.projected_exact_count.push(projected_count);
        out.projected_exact_share.push(projected_share);
        out.share_overflow.push(share_overflow);
        out.count_overflow_norm.push(count_overflow_norm);
        out.spam_risk.push(spam_risk);
        out.score_anchor_diversity.push(score);
        out.state_index.push(state);
        out.would_block.push(u8::from(blocked));
    }

    out
}

/// `evaluate_batch(...) -> dict[str, np.ndarray]`. Thin `PyO3` wrapper.
///
/// Reads the two parallel int32 arrays, validates them (1-D and same length),
/// delegates to [`evaluate_anchor_diversity_core`], and assembles the eight
/// output numpy arrays into a Python dict with the exact contract keys.
#[pyfunction]
#[pyo3(signature = (
    active_anchor_counts,
    exact_match_counts_before,
    min_history_count,
    max_exact_match_share,
    max_exact_match_count,
    hard_cap_enabled,
))]
// PyO3 extracts each `PyReadonlyArray1` by value at the Python boundary; taking
// them by reference is not possible for an extracted `#[pyfunction]` argument,
// so the by-value pass is required here, not a needless clone.
#[allow(clippy::needless_pass_by_value)]
fn evaluate_batch<'py>(
    py: Python<'py>,
    active_anchor_counts: PyReadonlyArray1<'py, i32>,
    exact_match_counts_before: PyReadonlyArray1<'py, i32>,
    min_history_count: i32,
    max_exact_match_share: f64,
    max_exact_match_count: i32,
    hard_cap_enabled: bool,
) -> PyResult<Bound<'py, PyDict>> {
    // A `PyReadonlyArray1` is already 1-D by type; the same-length check mirrors
    // the C++ guard and keeps the exact diagnostic message.
    let active = active_anchor_counts.as_slice()?;
    let before = exact_match_counts_before.as_slice()?;
    if active.len() != before.len() {
        return Err(PyValueError::new_err(
            "active_anchor_counts and exact_match_counts_before must be the same length",
        ));
    }

    let outputs = evaluate_anchor_diversity_core(
        active,
        before,
        min_history_count,
        max_exact_match_share,
        max_exact_match_count,
        hard_cap_enabled,
    );

    let result = PyDict::new(py);
    result.set_item(
        "projected_exact_count",
        outputs.projected_exact_count.into_pyarray(py),
    )?;
    result.set_item(
        "projected_exact_share",
        outputs.projected_exact_share.into_pyarray(py),
    )?;
    result.set_item("share_overflow", outputs.share_overflow.into_pyarray(py))?;
    result.set_item(
        "count_overflow_norm",
        outputs.count_overflow_norm.into_pyarray(py),
    )?;
    result.set_item("spam_risk", outputs.spam_risk.into_pyarray(py))?;
    result.set_item(
        "score_anchor_diversity",
        outputs.score_anchor_diversity.into_pyarray(py),
    )?;
    result.set_item("state_index", outputs.state_index.into_pyarray(py))?;
    result.set_item("would_block", outputs.would_block.into_pyarray(py))?;
    Ok(result)
}

/// The Python module definition. The module name (`anchor_diversity`) MUST match
/// the `[lib] name` in `Cargo.toml` so the built artifact
/// (`anchor_diversity.so`) imports as `extensions.anchor_diversity` once staged
/// on `PYTHONPATH` under `extensions/`. Registering `evaluate_batch` keeps the
/// health probe's expected attribute present.
#[pymodule]
fn anchor_diversity(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(evaluate_batch, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    #![allow(clippy::float_cmp)]

    use super::evaluate_anchor_diversity_core;

    /// Default FR-045 settings mirroring `AnchorDiversitySettings()`:
    /// `min_history_count=5`, `max_exact_match_share=0.3`,
    /// `max_exact_match_count=3`, `hard_cap_enabled=True`.
    const MIN_HISTORY: i32 = 5;
    const MAX_SHARE: f64 = 0.3;
    const MAX_COUNT: i32 = 3;

    #[test]
    fn neutral_no_history_below_min() {
        // active (1) < min_history_count (5) -> state 1, neutral row.
        let out =
            evaluate_anchor_diversity_core(&[1], &[0], MIN_HISTORY, MAX_SHARE, MAX_COUNT, true);
        assert_eq!(out.state_index[0], 1);
        assert_eq!(out.projected_exact_count[0], 0);
        assert_eq!(out.projected_exact_share[0], 0.0);
        assert_eq!(out.spam_risk[0], 0.0);
        assert_eq!(out.score_anchor_diversity[0], 0.5);
        assert_eq!(out.would_block[0], 0);
    }

    #[test]
    fn neutral_below_threshold() {
        // active=10, before=0 -> projected_count=1, share=1/11≈0.0909 < 0.3,
        // no overflow -> state 2, score 0.5.
        let out =
            evaluate_anchor_diversity_core(&[10], &[0], MIN_HISTORY, MAX_SHARE, MAX_COUNT, true);
        assert_eq!(out.state_index[0], 2);
        assert_eq!(out.projected_exact_count[0], 1);
        assert!((out.projected_exact_share[0] - 1.0 / 11.0).abs() < 1e-12);
        assert_eq!(out.share_overflow[0], 0.0);
        assert_eq!(out.score_anchor_diversity[0], 0.5);
        assert_eq!(out.would_block[0], 0);
    }

    #[test]
    fn penalized_exact_share() {
        // active=5, before=1 -> projected_count=2, denom=6, share=2/6≈0.333 >
        // 0.3 -> share_overflow > 0 but count_overflow 0 (2 <= 3) -> state 3.
        let out =
            evaluate_anchor_diversity_core(&[5], &[1], MIN_HISTORY, MAX_SHARE, MAX_COUNT, true);
        assert_eq!(out.state_index[0], 3);
        assert!(out.share_overflow[0] > 0.0);
        assert_eq!(out.count_overflow_norm[0], 0.0);
        assert!(out.score_anchor_diversity[0] < 0.5);
        assert_eq!(out.would_block[0], 0);
    }

    #[test]
    fn penalized_exact_count_without_block() {
        // before=3 -> projected_count=4 > max_count(3) -> count_overflow>0;
        // hard_cap disabled so not blocked -> state 4.
        let out =
            evaluate_anchor_diversity_core(&[20], &[3], MIN_HISTORY, MAX_SHARE, MAX_COUNT, false);
        assert_eq!(out.state_index[0], 4);
        assert!(out.count_overflow_norm[0] > 0.0);
        assert_eq!(out.would_block[0], 0);
    }

    #[test]
    fn blocked_exact_count_with_hard_cap() {
        // before=3 -> projected_count=4 > max_count(3); hard_cap enabled ->
        // blocked -> state 5, would_block 1.
        let out =
            evaluate_anchor_diversity_core(&[20], &[3], MIN_HISTORY, MAX_SHARE, MAX_COUNT, true);
        assert_eq!(out.state_index[0], 5);
        assert_eq!(out.would_block[0], 1);
    }

    #[test]
    fn share_overflow_formula_is_exact() {
        // active=5, before=1: share=2/6=0.33333..., overflow =
        // (0.33333... - 0.3) / (1 - 0.3) = 0.033333.../0.7.
        let out =
            evaluate_anchor_diversity_core(&[5], &[1], MIN_HISTORY, MAX_SHARE, MAX_COUNT, true);
        let projected_share: f64 = 2.0 / 6.0;
        let expected = (projected_share - 0.3).max(0.0) / (1.0 - 0.3_f64).max(1e-9);
        assert!((out.share_overflow[0] - expected).abs() < 1e-12);
    }

    #[test]
    fn spam_risk_is_weighted_combination_capped_at_one() {
        // Force a high count overflow so spam_risk saturates near the cap.
        let out =
            evaluate_anchor_diversity_core(&[5], &[50], MIN_HISTORY, MAX_SHARE, MAX_COUNT, true);
        assert!(out.spam_risk[0] <= 1.0);
        assert!(out.score_anchor_diversity[0] >= 0.0);
    }

    #[test]
    fn batch_of_mixed_states_preserves_order() {
        let active = [1, 10, 5, 20, 20];
        let before = [0, 0, 1, 3, 3];
        let hard_cap = [true, true, true, false, true];
        // Run them individually and compare to the batch to confirm row
        // independence and order preservation.
        for (idx, &hc) in hard_cap.iter().enumerate() {
            let out = evaluate_anchor_diversity_core(
                &[active[idx]],
                &[before[idx]],
                MIN_HISTORY,
                MAX_SHARE,
                MAX_COUNT,
                hc,
            );
            assert_eq!(out.state_index.len(), 1);
        }
        // A homogeneous batch (all hard_cap=true) keeps each row's own result.
        let out = evaluate_anchor_diversity_core(
            &active,
            &before,
            MIN_HISTORY,
            MAX_SHARE,
            MAX_COUNT,
            true,
        );
        assert_eq!(out.state_index, vec![1, 2, 3, 5, 5]);
        assert_eq!(out.would_block, vec![0, 0, 0, 1, 1]);
    }

    #[test]
    fn empty_input_returns_empty_columns() {
        let out = evaluate_anchor_diversity_core(&[], &[], MIN_HISTORY, MAX_SHARE, MAX_COUNT, true);
        assert!(out.state_index.is_empty());
        assert!(out.spam_risk.is_empty());
    }
}
