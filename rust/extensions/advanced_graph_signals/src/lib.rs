use numpy::{IntoPyArray, PyReadonlyArray1};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyDict;

/// Outputs for the 6 advanced graph signals.
#[derive(Debug, Default, Clone, PartialEq)]
pub struct AdvancedGraphSignalsOutputs {
    pub score_tosd: Vec<f64>,
    pub score_dstp: Vec<f64>,
    pub score_icpc: Vec<f64>,
    pub score_sbma: Vec<f64>,
    pub score_rgsd: Vec<f64>,
    pub score_csbr: Vec<f64>,
}

impl AdvancedGraphSignalsOutputs {
    fn with_capacity(count: usize) -> Self {
        Self {
            score_tosd: Vec::with_capacity(count),
            score_dstp: Vec::with_capacity(count),
            score_icpc: Vec::with_capacity(count),
            score_sbma: Vec::with_capacity(count),
            score_rgsd: Vec::with_capacity(count),
            score_csbr: Vec::with_capacity(count),
        }
    }
}

/// Map a non-finite value (NaN / +-inf) to the neutral 0.0 fallback.
///
/// `f64::clamp` propagates NaN, so a NaN input would otherwise leak straight to
/// the output. Every signal sanitises through this before clamping so a corrupt
/// precompute cell degrades to neutral instead of poisoning the ranking score.
#[inline]
const fn finite_or_zero(value: f64) -> f64 {
    if value.is_finite() {
        value
    } else {
        0.0
    }
}

/// Core arithmetic for the 6 advanced graph signals (FR-260 to FR-265).
#[must_use]
#[allow(clippy::too_many_arguments)]
pub fn evaluate_advanced_graph_signals_core(
    spectral_scores: &[f64],
    tosd_filter_strength: f64,
    transition_counts: &[i32],
    out_degrees: &[i32],
    dstp_smoothing_alpha: f64,
    local_degrees: &[i32],
    global_degrees: &[i32],
    block_probabilities: &[f64],
    flat_distances: &[f64],
    density_gradients: &[f64],
    rgsd_curvature_penalty: f64,
    is_cross_silo: &[u8],
    persona_matches: &[f64],
    csbr_min_overlap_threshold: f64,
) -> AdvancedGraphSignalsOutputs {
    let count = spectral_scores.len();
    let mut out = AdvancedGraphSignalsOutputs::with_capacity(count);

    for i in 0..count {
        // FR-260: TOSD (Time-as-Operator Spectral Decay).
        // Low-pass spectral filter H(lambda) = 1 / (1 + alpha * lambda) over the
        // normalized-Laplacian eigenvalue lambda (>= 0), so lambda = 0 (isolated /
        // perfectly stable node) -> 1.0 per fr260-tosd.md edge cases.
        let lambda = spectral_scores[i];
        let tosd = 1.0 / tosd_filter_strength.mul_add(lambda, 1.0);
        out.score_tosd.push(finite_or_zero(tosd).clamp(0.0, 1.0));

        // FR-261: DSTP (Directed Sequential Transition Probability).
        // Smoothed P(B|A) = count(A->B) / (count(A->*) + alpha). The pseudo-count
        // alpha shrinks low-traffic pairs toward the neutral 0.0 prior (a single
        // A->B session yields 1/(1+alpha), not 1.0), and a cold-start node with no
        // transitions yields 0/(0+alpha) = 0.0 -- the neutral fallback the spec
        // requires (fr261-dstp.md), not the maximum score.
        let t_count = f64::from(transition_counts[i]);
        let out_deg = f64::from(out_degrees[i]);
        let dstp = t_count / (out_deg + dstp_smoothing_alpha).max(1e-9);
        out.score_dstp.push(finite_or_zero(dstp).clamp(0.0, 1.0));

        // FR-262: ICPC (In-Community Popularity Contrast).
        // log(1 + d_local) / log(1 + d_global); the log base cancels in the ratio.
        // d_local <= d_global, so the true ratio is in [0, 1].
        let d_local = f64::from(local_degrees[i]);
        let d_global = f64::from(global_degrees[i]);
        let num = d_local.ln_1p();
        let den = d_global.ln_1p().max(1e-9);
        let icpc = num / den;
        out.score_icpc.push(finite_or_zero(icpc).clamp(0.0, 1.0));

        // FR-263: SBMA (Stochastic Block Model Affinity).
        // O(1) lookup of the inter-block link probability (resolved Python-side);
        // the kernel only bounds it to the [0, 1] probability range.
        let sbma = block_probabilities[i];
        out.score_sbma.push(finite_or_zero(sbma).clamp(0.0, 1.0));

        // FR-264: RGSD (Riemannian Geodesic Semantic Distance).
        // Geodesic distance D_geo = D_flat * (1 + k * density_gradient) (fr264).
        // The signal is a relevance score (higher = closer), and the inputs are
        // cosine *distances* in [0, 1] (a missing pair defaults to 1.0 = farthest),
        // so we invert to a similarity: score = 1 - D_geo, clamped to [0, 1]. The
        // 1 - x map and its saturation are an implementation choice recorded in the
        // spec; the RGSD slice revisits the normalization with real data.
        let flat_dist = flat_distances[i];
        let gradient = density_gradients[i];
        let rgsd = flat_dist * rgsd_curvature_penalty.mul_add(gradient, 1.0);
        let rgsd_score = 1.0 - rgsd;
        out.score_rgsd
            .push(finite_or_zero(rgsd_score).clamp(0.0, 1.0));

        // FR-265: CSBR (Cross-Silo Bridging Reward).
        // R = indicator(Silo_A != Silo_B) * ReLU(PersonaMatch - Threshold), then
        // rescaled by 1/(1 - Threshold) so a perfect bridge reaches 1.0 and can
        // cancel the cross-silo penalty (fr265-csbr.md). PersonaMatch is a topic
        // *similarity* in [0, 1] (the Python side converts LDA Jensen-Shannon
        // divergence to similarity before passing it in).
        let cross = is_cross_silo[i] != 0;
        let p_match = persona_matches[i];
        let csbr = if cross {
            (p_match - csbr_min_overlap_threshold).max(0.0)
        } else {
            0.0
        };
        let csbr_norm = csbr / (1.0 - csbr_min_overlap_threshold).max(1e-9);
        out.score_csbr
            .push(finite_or_zero(csbr_norm).clamp(0.0, 1.0));
    }

    out
}

#[pyfunction]
#[pyo3(signature = (
    spectral_scores,
    tosd_filter_strength,
    transition_counts,
    out_degrees,
    dstp_smoothing_alpha,
    local_degrees,
    global_degrees,
    block_probabilities,
    flat_distances,
    density_gradients,
    rgsd_curvature_penalty,
    is_cross_silo,
    persona_matches,
    csbr_min_overlap_threshold,
))]
#[allow(clippy::needless_pass_by_value, clippy::too_many_arguments)]
fn evaluate_batch<'py>(
    py: Python<'py>,
    spectral_scores: PyReadonlyArray1<'py, f64>,
    tosd_filter_strength: f64,
    transition_counts: PyReadonlyArray1<'py, i32>,
    out_degrees: PyReadonlyArray1<'py, i32>,
    dstp_smoothing_alpha: f64,
    local_degrees: PyReadonlyArray1<'py, i32>,
    global_degrees: PyReadonlyArray1<'py, i32>,
    block_probabilities: PyReadonlyArray1<'py, f64>,
    flat_distances: PyReadonlyArray1<'py, f64>,
    density_gradients: PyReadonlyArray1<'py, f64>,
    rgsd_curvature_penalty: f64,
    is_cross_silo: PyReadonlyArray1<'py, u8>,
    persona_matches: PyReadonlyArray1<'py, f64>,
    csbr_min_overlap_threshold: f64,
) -> PyResult<Bound<'py, PyDict>> {
    let s_scores = spectral_scores.as_slice()?;
    let t_counts = transition_counts.as_slice()?;
    let o_degrees = out_degrees.as_slice()?;
    let l_degrees = local_degrees.as_slice()?;
    let g_degrees = global_degrees.as_slice()?;
    let b_probs = block_probabilities.as_slice()?;
    let f_dists = flat_distances.as_slice()?;
    let d_grads = density_gradients.as_slice()?;
    let cross = is_cross_silo.as_slice()?;
    let p_matches = persona_matches.as_slice()?;

    let len = s_scores.len();
    if t_counts.len() != len
        || o_degrees.len() != len
        || l_degrees.len() != len
        || g_degrees.len() != len
        || b_probs.len() != len
        || f_dists.len() != len
        || d_grads.len() != len
        || cross.len() != len
        || p_matches.len() != len
    {
        return Err(PyValueError::new_err(
            "All input arrays must be the same length",
        ));
    }

    let outputs = evaluate_advanced_graph_signals_core(
        s_scores,
        tosd_filter_strength,
        t_counts,
        o_degrees,
        dstp_smoothing_alpha,
        l_degrees,
        g_degrees,
        b_probs,
        f_dists,
        d_grads,
        rgsd_curvature_penalty,
        cross,
        p_matches,
        csbr_min_overlap_threshold,
    );

    let result = PyDict::new(py);
    result.set_item("score_tosd", outputs.score_tosd.into_pyarray(py))?;
    result.set_item("score_dstp", outputs.score_dstp.into_pyarray(py))?;
    result.set_item("score_icpc", outputs.score_icpc.into_pyarray(py))?;
    result.set_item("score_sbma", outputs.score_sbma.into_pyarray(py))?;
    result.set_item("score_rgsd", outputs.score_rgsd.into_pyarray(py))?;
    result.set_item("score_csbr", outputs.score_csbr.into_pyarray(py))?;

    Ok(result)
}

#[pymodule]
fn advanced_graph_signals(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(evaluate_batch, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;
    use proptest::prelude::*;

    /// Assert two floats are equal within a tight tolerance.
    fn approx(actual: f64, expected: f64) {
        assert!(
            (actual - expected).abs() < 1e-9,
            "expected {expected}, got {actual}"
        );
    }

    /// Evaluate one candidate with the given per-signal inputs and default params.
    #[allow(clippy::too_many_arguments)]
    fn eval_one(
        spectral: f64,
        t_count: i32,
        out_deg: i32,
        d_local: i32,
        d_global: i32,
        block_prob: f64,
        flat: f64,
        gradient: f64,
        cross: u8,
        persona: f64,
    ) -> AdvancedGraphSignalsOutputs {
        evaluate_advanced_graph_signals_core(
            &[spectral],
            0.8,
            &[t_count],
            &[out_deg],
            5.0,
            &[d_local],
            &[d_global],
            &[block_prob],
            &[flat],
            &[gradient],
            1.5,
            &[cross],
            &[persona],
            0.7,
        )
    }

    #[test]
    fn known_answers_match_hand_computed_values() {
        let out = eval_one(2.0, 5, 10, 5, 20, 0.75, 0.2, 1.0, 1, 0.85);
        // TOSD: 1 / (1 + 0.8*2.0) = 1/2.6
        approx(out.score_tosd[0], 1.0 / 2.6);
        // DSTP: 5 / (10 + 5) = 1/3
        approx(out.score_dstp[0], 5.0 / 15.0);
        // ICPC: log base 21 of 6 == ln(6) / ln(21)
        approx(out.score_icpc[0], 6.0_f64.log(21.0));
        // SBMA: passthrough lookup
        approx(out.score_sbma[0], 0.75);
        // RGSD: 1 - 0.2*(1 + 1.5*1.0) = 1 - 0.5
        approx(out.score_rgsd[0], 0.5);
        // CSBR: (0.85 - 0.7) / (1 - 0.7) = 0.15/0.3
        approx(out.score_csbr[0], 0.5);
    }

    #[test]
    fn dstp_cold_start_is_neutral_zero_not_max() {
        // A node with no recorded transitions and no out-degree must score the
        // neutral 0.0, NOT the maximum (the prior bug returned ~1.0 here).
        let out = eval_one(0.0, 0, 0, 0, 0, 0.0, 1.0, 0.0, 0, 0.0);
        approx(out.score_dstp[0], 0.0);
    }

    #[test]
    fn tosd_isolated_node_is_one() {
        // lambda = 0 (isolated / perfectly stable) -> H(0) = 1.0 (fr260 edge case).
        let out = eval_one(0.0, 0, 0, 0, 0, 0.0, 1.0, 0.0, 0, 0.0);
        approx(out.score_tosd[0], 1.0);
    }

    #[test]
    fn csbr_same_silo_is_zero() {
        // No cross-silo bridge -> no reward, even with a perfect persona match.
        let out = eval_one(1.0, 0, 0, 0, 0, 0.0, 1.0, 0.0, 0, 1.0);
        approx(out.score_csbr[0], 0.0);
    }

    #[test]
    fn non_finite_inputs_degrade_to_zero() {
        // NaN / inf must not leak through clamp; each signal falls back to 0.0.
        let out = eval_one(
            f64::NAN,
            0,
            0,
            0,
            0,
            f64::INFINITY,
            f64::NAN,
            f64::NAN,
            1,
            f64::NAN,
        );
        approx(out.score_tosd[0], 0.0);
        approx(out.score_sbma[0], 0.0);
        approx(out.score_rgsd[0], 0.0);
        approx(out.score_csbr[0], 0.0);
    }

    proptest! {
        /// Every signal output is finite and bounded to [0, 1] for any plausible
        /// finite inputs (the [0, 1] invariant all six specs claim).
        #[test]
        fn prop_outputs_always_bounded(
            spectral in 0.0f64..1_000.0,
            t_count in 0i32..100_000,
            out_deg in 0i32..100_000,
            d_local in 0i32..100_000,
            d_global in 0i32..100_000,
            block_prob in 0.0f64..1.0,
            flat in 0.0f64..1.0,
            gradient in 0.0f64..10.0,
            cross in 0u8..2,
            persona in 0.0f64..1.0,
        ) {
            let out = eval_one(
                spectral, t_count, out_deg, d_local, d_global,
                block_prob, flat, gradient, cross, persona,
            );
            for v in [
                out.score_tosd[0], out.score_dstp[0], out.score_icpc[0],
                out.score_sbma[0], out.score_rgsd[0], out.score_csbr[0],
            ] {
                prop_assert!(v.is_finite());
                prop_assert!((0.0..=1.0).contains(&v));
            }
        }
    }
}
