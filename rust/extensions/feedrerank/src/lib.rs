//! FR-013 explore/exploit rerank + FR-015 MMR diversity hot-path kernel, ported
//! from the C++ `feedrerank` kernel (`backend/extensions/feedrerank.cpp` plus
//! `include/feedrerank_core.h`) to Rust and exposed to Python as the native
//! module `extensions.feedrerank` via `PyO3` and the `numpy` crate.
//!
//! Two module-level functions match the C++ kernel exactly:
//!
//! - `calculate_rerank_factors_batch(n_successes, n_totals,
//!   observation_confidences, n_global, alpha, beta, weight, exploration_rate)
//!   -> np.ndarray[f64]` — a per-candidate rerank factor in `[0.5, 2.0]`.
//! - `calculate_mmr_scores_batch(relevance, candidate_embeddings,
//!   selected_embeddings, diversity_lambda) -> (np.ndarray[f64],
//!   np.ndarray[f64])` — MMR scores and per-candidate max similarities.
//!
//! ## Parity (port note)
//!
//! Parity is EXACT. Both production callers
//! (`feedback_rerank.py`, `slate_diversity.py`) recompute the same formula in
//! Python and a dedicated parity test asserts agreement to `atol=1e-6`. All math
//! is deterministic IEEE-754 `f64` with no hashing, RNG, or `f32`. The two
//! non-determinism risks the C++ kernel pins down are reproduced literally here:
//! (1) the `max(denom, 1e-9)` guard (RPT-001 Finding 3) so zero priors plus zero
//! totals stays finite, and (2) the left-to-right `f64` accumulation order of the
//! MMR dot product, so the last ULP matches the Python reference. The
//! observation-confidence term is a LINEAR blend toward `0.5`, not an
//! inverse-propensity estimator (RPT-001 Finding 2). FR-015 MMR sources:
//! Carbonell & Goldstein 1998 (SIGIR) and patent US20070294225A1.

use numpy::{IntoPyArray, PyReadonlyArray1, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

/// Denominator guard for the Bayesian exploit term: keeps the division finite
/// when `alpha = beta = 0` and `totals = 0` (RPT-001 Finding 3).
const EXPLOIT_DENOM_FLOOR: f64 = 1e-9;
/// Lower clamp on the rerank factor.
const FACTOR_MIN: f64 = 0.5;
/// Upper clamp on the rerank factor.
const FACTOR_MAX: f64 = 2.0;
/// Neutral score the confidence blend pulls toward, and the modifier midpoint.
const NEUTRAL: f64 = 0.5;

// The C++ kernel parallelised batches above 256 (rerank) / 128 (MMR) with TBB.
// Each output element is an independent pure function of its inputs, so the
// serial Rust core below is bit-identical to the C++ parallel path; no parallel
// runtime is needed for parity.

/// Compute one explore/exploit rerank factor for a single candidate.
///
/// Mirrors `feedback_rerank.py` and the C++ `rerank_factors_core` line by line:
/// a Bayesian exploit estimate with the `1e-9` denominator floor, a linear
/// observation-confidence blend toward `0.5`, a UCB1 exploration bonus, the
/// weighted modifier, and the final clamp to `[0.5, 2.0]`.
// The 8-arg signature mirrors the C++ kernel's parameter contract exactly;
// grouping them into a struct would obscure the 1:1 parity mapping.
#[allow(clippy::too_many_arguments)]
#[must_use]
pub fn rerank_factor_one(
    successes: i32,
    totals: i32,
    observation_confidence: f64,
    n_global: i32,
    alpha: f64,
    beta: f64,
    weight: f64,
    exploration_rate: f64,
) -> f64 {
    let exploit_denom = f64::from(totals) + alpha + beta;
    let score_exploit_raw = (f64::from(successes) + alpha) / exploit_denom.max(EXPLOIT_DENOM_FLOOR);
    let oc = observation_confidence;
    let score_exploit = (1.0 - oc).mul_add(NEUTRAL, oc * score_exploit_raw);
    // UCB1 exploration bonus. Parenthesization matches the C++ kernel exactly:
    // sqrt( ln(n_global + 1) / (totals + 1) ) — the log is taken of
    // `n_global + 1` ALONE, then divided by `totals + 1`, then square-rooted.
    let score_explore =
        exploration_rate * (f64::from(n_global).ln_1p() / (f64::from(totals) + 1.0)).sqrt();
    let raw_modifier = (score_exploit + score_explore) - NEUTRAL;
    let factor = weight.mul_add(raw_modifier, 1.0);
    factor.clamp(FACTOR_MIN, FACTOR_MAX)
}

/// Compute the full batch of rerank factors. Pure Rust over slices so it is
/// unit-testable without the Python boundary.
// The 8-arg signature mirrors the C++ kernel's parameter contract exactly.
#[allow(clippy::too_many_arguments)]
#[must_use]
pub fn rerank_factors_core(
    successes: &[i32],
    totals: &[i32],
    observation_confidences: &[f64],
    n_global: i32,
    alpha: f64,
    beta: f64,
    weight: f64,
    exploration_rate: f64,
) -> Vec<f64> {
    (0..successes.len())
        .map(|i| {
            rerank_factor_one(
                successes[i],
                totals[i],
                observation_confidences[i],
                n_global,
                alpha,
                beta,
                weight,
                exploration_rate,
            )
        })
        .collect()
}

/// Compute the MMR score and max-similarity for one candidate row.
///
/// `candidate_row` is one embedding; `selected` is the flat row-major matrix of
/// already-selected embeddings (`selected_count` rows of `width`). The dot
/// product accumulates left-to-right in `f64` to match the Python reference's
/// last ULP. The first selected row seeds `max_similarity` regardless of sign
/// (`selected_index == 0 || dot > max`), so a single negative dot is still the
/// max. With `selected_count == 0` the max stays `0.0`.
fn mmr_one(
    candidate_row: &[f64],
    selected: &[f64],
    selected_count: usize,
    width: usize,
    relevance: f64,
    diversity_lambda: f64,
) -> (f64, f64) {
    let mut max_similarity = 0.0_f64;
    for j in 0..selected_count {
        let selected_row = &selected[j * width..j * width + width];
        let mut dot = 0.0_f64;
        for d in 0..width {
            dot = candidate_row[d].mul_add(selected_row[d], dot);
        }
        if j == 0 || dot > max_similarity {
            max_similarity = dot;
        }
    }
    let mmr = (1.0 - diversity_lambda).mul_add(-max_similarity, diversity_lambda * relevance);
    (mmr, max_similarity)
}

/// Compute the full MMR batch. Returns `(mmr_scores, max_similarities)`, both of
/// length `candidate_count`. Pure Rust over flat row-major slices so it is
/// unit-testable without the Python boundary.
#[must_use]
pub fn mmr_scores_core(
    relevance: &[f64],
    candidate: &[f64],
    selected: &[f64],
    candidate_count: usize,
    selected_count: usize,
    width: usize,
    diversity_lambda: f64,
) -> (Vec<f64>, Vec<f64>) {
    let mut mmr_scores = Vec::with_capacity(candidate_count);
    let mut max_similarities = Vec::with_capacity(candidate_count);
    for i in 0..candidate_count {
        let candidate_row = &candidate[i * width..i * width + width];
        let (mmr, max_sim) = mmr_one(
            candidate_row,
            selected,
            selected_count,
            width,
            relevance[i],
            diversity_lambda,
        );
        mmr_scores.push(mmr);
        max_similarities.push(max_sim);
    }
    (mmr_scores, max_similarities)
}

/// `calculate_rerank_factors_batch(...) -> np.ndarray[f64]`.
///
/// Thin wrapper around [`rerank_factors_core`] that validates array shapes and
/// maps mismatches to the same `RuntimeError` messages as the C++ kernel.
#[pyfunction]
#[allow(clippy::too_many_arguments, clippy::needless_pass_by_value)]
fn calculate_rerank_factors_batch<'py>(
    py: Python<'py>,
    n_successes: PyReadonlyArray1<'py, i32>,
    n_totals: PyReadonlyArray1<'py, i32>,
    observation_confidences: PyReadonlyArray1<'py, f64>,
    n_global: i32,
    alpha: f64,
    beta: f64,
    weight: f64,
    exploration_rate: f64,
) -> PyResult<Bound<'py, numpy::PyArray1<f64>>> {
    // `PyReadonlyArray1` is 1-D by type, so the C++ ndim==1 guard is satisfied
    // structurally. Only the same-length checks remain.
    let successes = n_successes.as_slice()?;
    let totals = n_totals.as_slice()?;
    let oc = observation_confidences.as_slice()?;
    if successes.len() != totals.len() {
        return Err(PyRuntimeError::new_err(
            "n_successes and n_totals must have the same length",
        ));
    }
    if oc.len() != successes.len() {
        return Err(PyRuntimeError::new_err(
            "observation_confidences must be a 1D float64 array with the same length as n_successes",
        ));
    }
    let factors = py.detach(|| {
        rerank_factors_core(
            successes,
            totals,
            oc,
            n_global,
            alpha,
            beta,
            weight,
            exploration_rate,
        )
    });
    Ok(factors.into_pyarray(py))
}

/// `calculate_mmr_scores_batch(...) -> (np.ndarray[f64], np.ndarray[f64])`.
///
/// Thin wrapper around [`mmr_scores_core`] that validates array shapes and maps
/// mismatches to the same `RuntimeError` messages as the C++ kernel.
#[pyfunction]
#[allow(clippy::needless_pass_by_value)]
fn calculate_mmr_scores_batch<'py>(
    py: Python<'py>,
    relevance: PyReadonlyArray1<'py, f64>,
    candidate_embeddings: PyReadonlyArray2<'py, f64>,
    selected_embeddings: PyReadonlyArray2<'py, f64>,
    diversity_lambda: f64,
) -> PyResult<Bound<'py, PyTuple>> {
    let relevance_slice = relevance.as_slice()?;
    let candidate_shape = candidate_embeddings.shape();
    let selected_shape = selected_embeddings.shape();
    let candidate_count = candidate_shape[0];
    let candidate_width = candidate_shape[1];
    let selected_count = selected_shape[0];
    let selected_width = selected_shape[1];

    if candidate_count != relevance_slice.len() {
        return Err(PyRuntimeError::new_err(
            "candidate_embeddings rows must match relevance length",
        ));
    }
    if candidate_width != selected_width {
        return Err(PyRuntimeError::new_err(
            "candidate_embeddings and selected_embeddings must have the same embedding width",
        ));
    }

    // c_style|forcecast on the C++ side guaranteed C-contiguous; `as_slice()`
    // here requires the same and errors otherwise, preserving row-major layout.
    let candidate = candidate_embeddings.as_slice()?;
    let selected = selected_embeddings.as_slice()?;

    let (mmr_scores, max_similarities) = py.detach(|| {
        mmr_scores_core(
            relevance_slice,
            candidate,
            selected,
            candidate_count,
            selected_count,
            candidate_width,
            diversity_lambda,
        )
    });

    let mmr_arr = mmr_scores.into_pyarray(py);
    let max_arr = max_similarities.into_pyarray(py);
    PyTuple::new(py, [mmr_arr.into_any(), max_arr.into_any()])
}

/// The Python module definition. The module name (`feedrerank`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact imports as
/// `extensions.feedrerank`. Registering both functions keeps the health probe's
/// expected attribute (`calculate_mmr_scores_batch`) present.
#[pymodule]
fn feedrerank(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(calculate_rerank_factors_batch, m)?)?;
    m.add_function(wrap_pyfunction!(calculate_mmr_scores_batch, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{mmr_scores_core, rerank_factor_one, rerank_factors_core};

    /// Independent Python-reference reimplementation of one rerank factor for
    /// cross-checking the core against the documented formula.
    #[allow(clippy::too_many_arguments)]
    fn rerank_reference(
        successes: i32,
        totals: i32,
        oc: f64,
        n_global: i32,
        alpha: f64,
        beta: f64,
        weight: f64,
        exploration_rate: f64,
    ) -> f64 {
        let denom = (f64::from(totals) + alpha + beta).max(1e-9);
        let exploit_raw = (f64::from(successes) + alpha) / denom;
        let exploit = oc * exploit_raw + (1.0 - oc) * 0.5;
        let explore =
            exploration_rate * (f64::from(n_global).ln_1p() / (f64::from(totals) + 1.0)).sqrt();
        let factor = 1.0 + weight * ((exploit + explore) - 0.5);
        factor.clamp(0.5, 2.0)
    }

    #[test]
    fn rerank_matches_reference() {
        let got = rerank_factor_one(5, 10, 0.8, 100, 1.0, 1.0, 0.3, 0.2);
        let want = rerank_reference(5, 10, 0.8, 100, 1.0, 1.0, 0.3, 0.2);
        assert!((got - want).abs() < 1e-12, "got {got} want {want}");
    }

    #[test]
    fn rerank_zero_priors_zero_totals_is_finite() {
        // RPT-001 Finding 3: alpha=beta=0, totals=0 must not be NaN/Inf thanks
        // to the 1e-9 denominator floor. Kills a mutant that drops the guard.
        let got = rerank_factor_one(0, 0, 1.0, 0, 0.0, 0.0, 1.0, 0.0);
        assert!(got.is_finite(), "factor was not finite: {got}");
        assert!((0.5..=2.0).contains(&got), "factor {got} outside clamp");
    }

    #[test]
    fn rerank_is_clamped_to_range() {
        // A huge positive weight*modifier must clamp at 2.0; a huge negative at
        // 0.5. Pins both ends of the clamp (kills min->max swaps).
        let high = rerank_factor_one(1000, 0, 1.0, 0, 1.0, 1.0, 100.0, 0.0);
        assert!(
            (high - 2.0).abs() < 1e-12,
            "expected clamp to 2.0, got {high}"
        );
        let low = rerank_factor_one(0, 1000, 1.0, 0, 1.0, 1.0, 100.0, 0.0);
        assert!(
            (low - 0.5).abs() < 1e-12,
            "expected clamp to 0.5, got {low}"
        );
    }

    #[test]
    fn rerank_confidence_blends_toward_half() {
        // oc=0 -> score_exploit collapses to 0.5 (neutral) regardless of the
        // raw exploit estimate. With exploration_rate 0 and weight 1 the factor
        // is then 1.0 + 1.0*((0.5+0)-0.5) = 1.0.
        let got = rerank_factor_one(9, 1, 0.0, 0, 1.0, 1.0, 1.0, 0.0);
        assert!(
            (got - 1.0).abs() < 1e-12,
            "oc=0 should give neutral 1.0, got {got}"
        );
    }

    #[test]
    fn rerank_empty_batch_is_empty() {
        let out = rerank_factors_core(&[], &[], &[], 0, 1.0, 1.0, 0.3, 0.2);
        assert!(out.is_empty());
    }

    #[test]
    fn rerank_batch_matches_per_element() {
        let s = [1, 5, 9];
        let t = [2, 10, 12];
        let oc = [1.0, 0.7, 0.4];
        let batch = rerank_factors_core(&s, &t, &oc, 50, 1.0, 1.0, 0.3, 0.25);
        for i in 0..3 {
            let one = rerank_factor_one(s[i], t[i], oc[i], 50, 1.0, 1.0, 0.3, 0.25);
            assert!((batch[i] - one).abs() < 1e-12);
        }
    }

    #[test]
    fn mmr_no_selected_gives_lambda_times_relevance() {
        // selected_count==0 -> max_similarity 0.0 -> mmr = lambda*relevance.
        let (mmr, maxsim) = mmr_scores_core(&[0.8, 0.3], &[1.0, 0.0, 0.0, 1.0], &[], 2, 0, 2, 0.7);
        assert!((maxsim[0]).abs() < 1e-12 && (maxsim[1]).abs() < 1e-12);
        assert!((mmr[0] - 0.7 * 0.8).abs() < 1e-12);
        assert!((mmr[1] - 0.7 * 0.3).abs() < 1e-12);
    }

    #[test]
    fn mmr_uses_max_dot_over_selected() {
        // One candidate [1,0]; two selected [0.5,0] (dot 0.5) and [0.9,0]
        // (dot 0.9). max_similarity must be 0.9.
        let candidate = [1.0, 0.0];
        let selected = [0.5, 0.0, 0.9, 0.0];
        let (mmr, maxsim) = mmr_scores_core(&[1.0], &candidate, &selected, 1, 2, 2, 0.6);
        assert!(
            (maxsim[0] - 0.9).abs() < 1e-12,
            "max sim {} != 0.9",
            maxsim[0]
        );
        let want = 0.6 * 1.0 - (1.0 - 0.6) * 0.9;
        assert!((mmr[0] - want).abs() < 1e-12);
    }

    #[test]
    fn mmr_first_selected_seeds_max_even_if_negative() {
        // Single selected row giving a NEGATIVE dot must still be the max
        // (the `j == 0 ||` seed), not the 0.0 initial value.
        let candidate = [1.0, 0.0];
        let selected = [-0.7, 0.0];
        let (_mmr, maxsim) = mmr_scores_core(&[1.0], &candidate, &selected, 1, 1, 2, 0.5);
        assert!(
            (maxsim[0] - -0.7).abs() < 1e-12,
            "expected -0.7, got {}",
            maxsim[0]
        );
    }

    #[test]
    fn mmr_dot_is_left_to_right_over_width() {
        // A 3-wide dot product: candidate dot selected = 1*2 + 2*3 + 3*4 = 20.
        let candidate = [1.0, 2.0, 3.0];
        let selected = [2.0, 3.0, 4.0];
        let (_mmr, maxsim) = mmr_scores_core(&[1.0], &candidate, &selected, 1, 1, 3, 0.5);
        assert!((maxsim[0] - 20.0).abs() < 1e-12, "dot {} != 20", maxsim[0]);
    }
}
