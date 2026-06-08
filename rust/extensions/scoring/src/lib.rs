//! Composite ranking-score hot-path kernel, ported from the C++ `scoring`
//! kernel (`backend/extensions/scoring.cpp`) to Rust and exposed to Python as
//! the native module `extensions.scoring` via `PyO3` + the `numpy` crate.
//!
//! The runtime calls `from extensions import scoring` and then
//! `scoring.calculate_composite_scores_full_batch(component_scores, weights,
//! silo_scores)` from `apps/pipeline/services/ranker.py`. This is the ranker's
//! final composite-score step: for each row `i` of a 2-D float32 component
//! matrix,
//!
//! ```text
//! out[i] = (i < len(silo_scores) ? silo_scores[i] : 0.0)
//!          + sum over j in [0, min(num_components, len(weights))) of
//!            component_scores[i][j] * weights[j]
//! ```
//!
//! and the result is a 1-D float32 array of length `num_rows`. Each row is one
//! link candidate, the columns are per-signal component scores, `weights` are
//! the per-signal blend weights, and `silo_scores` is an additive per-row
//! structural bonus.
//!
//! ## Parity basis (port note)
//!
//! Parity is by CONTRACT, not bit-for-bit. The C++ build compiled with
//! `-march=native` / `/arch:AVX2`, so the inner loop could auto-vectorize and
//! reorder `f32` additions, changing the last ULP across CPUs. The existing
//! parity tests (`test_parity_simple.py`, `apps/pipeline/tests.py`) compare with
//! `rtol=1e-5, atol=1e-5`. This port accumulates the dot product in `f32` with
//! a plain `+=` (NOT `mul_add`) to mirror the C++ source's two-rounding add and
//! stay closest to the reference. The `min(num_components, num_weights)`
//! truncation and the per-row silo seeding guard are part of the contract and
//! are preserved exactly.
//!
//! The compute core ([`score_full_batch_core`]) is plain Rust over flat slices
//! so it is unit-testable with `cargo test` without crossing the Python edge.
//!
//! Source: the linear scoring / weighted-linear-combination of ranking features
//! `f(c) = w·c + b` — Liu, "Learning to Rank for Information Retrieval"
//! (Foundations and Trends in IR, 2009, doi:10.1561/1500000016) §1.3, and the
//! additive feature blend in Robertson & Zaragoza 2009
//! (doi:10.1561/1500000019).

use numpy::{IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::prelude::*;

/// Compute the per-row composite score `silo[i] + dot(row_i, weights)` for a
/// flat row-major float32 component buffer.
///
/// `component_scores` is a flat `num_rows * num_components` row-major buffer.
/// For each row `i` the running sum is seeded with `silo_scores[i]` when
/// `i < silo_scores.len()` (else `0.0`), then the dot product runs over the
/// first `min(num_components, weights.len())` columns. Accumulation is `f32`
/// with a plain `+=` (two roundings per term) to mirror the C++ kernel.
///
/// Returns a `Vec<f32>` of length `num_rows`. Inputs are not mutated.
#[must_use]
pub fn score_full_batch_core(
    component_scores: &[f32],
    num_rows: usize,
    num_components: usize,
    weights: &[f32],
    silo_scores: &[f32],
) -> Vec<f32> {
    let mut out = Vec::with_capacity(num_rows);
    let term_count = num_components.min(weights.len());
    for i in 0..num_rows {
        // Per-row silo seeding guard: rows beyond the silo length seed 0.0,
        // exactly like the C++ `(silo_scores != nullptr) && i < num_silo` test.
        let mut sum: f32 = if i < silo_scores.len() {
            silo_scores[i]
        } else {
            0.0
        };
        let row_start = i * num_components;
        let row = &component_scores[row_start..row_start + num_components];
        for j in 0..term_count {
            // Plain `+=` (NOT mul_add): the C++ source does two roundings per
            // term, so we match that to stay within the 1e-5 contract.
            sum += row[j] * weights[j];
        }
        out.push(sum);
    }
    out
}

/// `calculate_composite_scores_full_batch(component_scores, weights,
/// silo_scores) -> np.ndarray[float32]`.
///
/// Computes the per-row composite score for a 2-D float32 component matrix and
/// returns a new 1-D float32 array of length `component_scores.shape[0]`. Inputs
/// are not mutated.
///
/// Using `PyReadonlyArray2` for `component_scores` and `PyReadonlyArray1` for
/// `weights`/`silo_scores` makes `PyO3`'s typed extractor enforce `ndim` and
/// `float32` dtype at the boundary, raising a clean Python `TypeError` on the
/// wrong shape. This is stricter (safer) than the C++ kernel's no-validation
/// behaviour and restores the validation intent of the old Python fallback. The
/// single production caller (`ranker.py`) always passes a 2-D float32 matrix and
/// 1-D float32 weights/silo, so it is unaffected.
#[pyfunction]
#[allow(clippy::needless_pass_by_value)]
fn calculate_composite_scores_full_batch<'py>(
    py: Python<'py>,
    component_scores: PyReadonlyArray2<'py, f32>,
    weights: PyReadonlyArray1<'py, f32>,
    silo_scores: PyReadonlyArray1<'py, f32>,
) -> PyResult<Bound<'py, PyArray1<f32>>> {
    let shape = component_scores.shape();
    let num_rows = shape[0];
    let num_components = shape[1];
    let component_slice = component_scores.as_slice()?;
    let weights_slice = weights.as_slice()?;
    let silo_slice = silo_scores.as_slice()?;

    let out = py.detach(|| {
        score_full_batch_core(
            component_slice,
            num_rows,
            num_components,
            weights_slice,
            silo_slice,
        )
    });
    Ok(out.into_pyarray(py))
}

/// The Python module definition. The module name (`scoring`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`scoring.so`) imports as
/// `extensions.scoring` once it is staged on `PYTHONPATH` under `extensions/`.
#[pymodule]
fn scoring(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(calculate_composite_scores_full_batch, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::score_full_batch_core;

    /// Tolerance for the `f32` accumulation parity assertions. Matches the
    /// `rtol=1e-5, atol=1e-5` the existing Python parity tests use.
    const TOL: f32 = 1e-5;

    /// `f32` left-to-right reference matching the core's accumulation order, so
    /// the parity test pins single-precision (NOT `f64`) accumulation.
    fn reference_f32(
        component_scores: &[f32],
        num_rows: usize,
        num_components: usize,
        weights: &[f32],
        silo: &[f32],
    ) -> Vec<f32> {
        let mut out = Vec::with_capacity(num_rows);
        let term_count = num_components.min(weights.len());
        for i in 0..num_rows {
            let mut sum: f32 = if i < silo.len() { silo[i] } else { 0.0 };
            for j in 0..term_count {
                sum += component_scores[i * num_components + j] * weights[j];
            }
            out.push(sum);
        }
        out
    }

    #[test]
    fn happy_path_silo_plus_dot_product() {
        // 3 rows x 2 components, len-2 weights, len-3 silo.
        // out[i] = silo[i] + c[i][0]*w[0] + c[i][1]*w[1].
        let comp = [1.0_f32, 2.0, 3.0, 4.0, 5.0, 6.0];
        let weights = [10.0_f32, 100.0];
        let silo = [0.5_f32, 1.5, 2.5];
        let out = score_full_batch_core(&comp, 3, 2, &weights, &silo);
        assert!((out[0] - (0.5 + 10.0 + 200.0)).abs() < TOL, "got {out:?}");
        assert!((out[1] - (1.5 + 30.0 + 400.0)).abs() < TOL, "got {out:?}");
        assert!((out[2] - (2.5 + 50.0 + 600.0)).abs() < TOL, "got {out:?}");
    }

    #[test]
    fn zero_rows_returns_empty() {
        let out = score_full_batch_core(&[], 0, 2, &[1.0, 1.0], &[]);
        assert!(out.is_empty(), "num_rows == 0 must return an empty vec");
    }

    #[test]
    fn weights_shorter_than_components_truncates_to_weights_len() {
        // 1 row x 3 components, but only 2 weights -> only first 2 terms summed.
        // Kills the `j < num_weights` guard mutant: column 2 (value 99) must be
        // ignored, so the result excludes 99 * (nonexistent weight).
        let comp = [1.0_f32, 2.0, 99.0];
        let weights = [10.0_f32, 100.0];
        let silo = [0.0_f32];
        let out = score_full_batch_core(&comp, 1, 3, &weights, &silo);
        assert!((out[0] - (10.0 + 200.0)).abs() < TOL, "got {out:?}");
    }

    #[test]
    fn weights_longer_than_components_truncates_to_components() {
        // 1 row x 2 components, but 3 weights -> only first 2 terms summed.
        // Kills the `j < num_components` guard mutant: the 3rd weight (1000) has
        // no matching column and must be ignored.
        let comp = [1.0_f32, 2.0];
        let weights = [10.0_f32, 100.0, 1000.0];
        let silo = [0.0_f32];
        let out = score_full_batch_core(&comp, 1, 2, &weights, &silo);
        assert!((out[0] - (10.0 + 200.0)).abs() < TOL, "got {out:?}");
    }

    #[test]
    fn silo_shorter_than_rows_seeds_zero_for_extra_rows() {
        // 2 rows but only 1 silo entry -> row 1 seeds 0.0.
        // Kills the `i < num_silo` guard mutant.
        let comp = [1.0_f32, 1.0];
        let weights = [2.0_f32];
        let silo = [7.0_f32]; // only row 0 gets a silo seed
        let out = score_full_batch_core(&comp, 2, 1, &weights, &silo);
        assert!((out[0] - (7.0 + 2.0)).abs() < TOL, "row 0 got {out:?}");
        assert!(
            (out[1] - 2.0).abs() < TOL,
            "row 1 must seed 0.0, got {out:?}"
        );
    }

    #[test]
    fn silo_added_exactly_once_as_bias() {
        // Zero weights so the dot product is 0; the output must equal silo
        // exactly. Kills the `sum = silo` vs `sum = 0` mutant and the
        // `+=` vs `=` seeding mutant.
        let comp = [5.0_f32, 9.0];
        let weights = [0.0_f32, 0.0];
        let silo = [3.0_f32];
        let out = score_full_batch_core(&comp, 1, 2, &weights, &silo);
        assert!((out[0] - 3.0).abs() < TOL, "got {out:?}");
    }

    #[test]
    fn parity_against_f32_left_to_right_reference() {
        // 100 rows, 8 components, deterministic pseudo-random float32 values,
        // mirroring test_parity_simple.py::test_scoring_parity. Assert
        // near-equality (1e-5) against an f32 left-to-right reference, pinning
        // single-precision accumulation (an f64 reference would mask drift).
        let num_rows = 100;
        let num_components = 8;
        let mut comp = Vec::with_capacity(num_rows * num_components);
        for i in 0..num_rows * num_components {
            // Bounded small magnitudes; cast is exact for these integers.
            #[allow(clippy::cast_precision_loss)]
            comp.push(((i % 37) as f32) * 0.013 - 0.25);
        }
        let weights: Vec<f32> = (0..num_components)
            .map(|j| {
                #[allow(clippy::cast_precision_loss)]
                let v = (j as f32) * 0.1 + 0.05;
                v
            })
            .collect();
        let silo: Vec<f32> = (0..num_rows)
            .map(|i| {
                #[allow(clippy::cast_precision_loss)]
                let v = (i as f32) * 0.001;
                v
            })
            .collect();

        let out = score_full_batch_core(&comp, num_rows, num_components, &weights, &silo);
        let expected = reference_f32(&comp, num_rows, num_components, &weights, &silo);
        assert_eq!(out.len(), num_rows);
        for (got, want) in out.iter().zip(expected.iter()) {
            let diff = (got - want).abs();
            let tol = TOL + TOL * want.abs();
            assert!(diff <= tol, "parity drift: got {got} want {want}");
        }
    }
}
