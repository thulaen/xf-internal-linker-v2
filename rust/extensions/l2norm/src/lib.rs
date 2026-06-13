//! L2 normalization hot-path kernel, ported from the C++ `l2norm` kernel
//! (`backend/extensions/l2norm.cpp`) to Rust and exposed to Python as the
//! native module `extensions.l2norm` via `PyO3` + the `numpy` crate.
//!
//! The runtime calls `from extensions import l2norm` and then
//! `l2norm.normalize_l2_batch(arr)` from
//! `apps/pipeline/services/embeddings.py::_l2_normalize`. The Python-callable
//! API matches the C++ kernel exactly:
//!
//! - [`normalize_l2`] — 1-D float32 array, normalized to unit L2 norm in place,
//!   returns `None`.
//! - [`normalize_l2_batch`] — 2-D C-contiguous float32 array; each row is
//!   normalized to unit L2 norm in place; a row whose norm is `<= 1e-10` is
//!   left unchanged; raises `ValueError("Input must be 2D")` when the input is
//!   not 2-D; returns `None`.
//!
//! The compute core ([`normalize_l2_slice`]) is plain Rust over an `&mut [f32]`
//! slice so it is unit-testable with `cargo test` without crossing the Python
//! boundary. The float32 arithmetic mirrors the C++ serial path bit-for-bit:
//! a single-precision running sum of squares, `sqrt`, then multiply by the
//! reciprocal norm.
//!
//! Source for the unit-norm + `1e-10` guard semantics: the C++ kernel this
//! replaces (`backend/extensions/l2norm.cpp`), and the FR-237 L2-norm audit
//! (Wang et al. 2017, NAACL §2; IEEE 754-2019 §5.4) documented in
//! `apps/pipeline/services/embeddings.py`.

use numpy::{PyReadwriteArray1, PyReadwriteArrayDyn, PyUntypedArrayMethods};
use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

/// Threshold below which a vector is treated as effectively zero and left
/// unchanged. Matches the C++ kernel's `1e-10F` guard exactly.
const MIN_NORM: f32 = 1e-10;

/// Normalize a single float32 row to unit L2 norm in place.
///
/// Computes `sum(v_i^2)` as a single-precision running sum, takes the
/// square root, and — only when the norm exceeds [`MIN_NORM`] — multiplies
/// every element by the reciprocal norm. A zero-length slice or a slice whose
/// norm is `<= MIN_NORM` is left unchanged, exactly like the C++ kernel.
pub fn normalize_l2_slice(values: &mut [f32]) {
    if values.is_empty() {
        return;
    }
    let mut sum_sq: f32 = 0.0;
    for &v in values.iter() {
        // Fused multiply-add: one rounding step instead of two, and it maps to
        // a single FMA instruction on hardware that has one. clippy's
        // `suboptimal_flops` flags the separate `+= v * v` form.
        sum_sq = v.mul_add(v, sum_sq);
    }
    let norm = sum_sq.sqrt();
    if norm > MIN_NORM {
        let inv_norm = 1.0 / norm;
        for v in values.iter_mut() {
            *v *= inv_norm;
        }
    }
}

/// Normalize each row of a flat row-major float32 buffer to unit L2 norm in
/// place. `cols` is the row stride; the buffer length must be `rows * cols`.
///
/// Each row is normalized independently via [`normalize_l2_slice`], so a row
/// whose norm is `<= MIN_NORM` is left unchanged while its neighbours are
/// normalized. A zero-row or zero-column buffer is a no-op.
pub fn normalize_l2_batch_buffer(buffer: &mut [f32], cols: usize) {
    if cols == 0 || buffer.is_empty() {
        return;
    }
    for row in buffer.chunks_mut(cols) {
        normalize_l2_slice(row);
    }
}

/// In-place L2 normalization for a 1-D float32 array.
///
/// Mirrors the C++ `normalize_l2`. The `numpy` crate gives a zero-copy
/// read-write view, so the caller's array is mutated directly and the function
/// returns `None`.
#[pyfunction]
fn normalize_l2(mut input: PyReadwriteArray1<'_, f32>) -> PyResult<()> {
    let slice = input.as_slice_mut().map_err(|err| {
        PyValueError::new_err(format!(
            "normalize_l2 requires a contiguous 1D float32 array: {err}"
        ))
    })?;
    normalize_l2_slice(slice);
    Ok(())
}

/// In-place row-wise L2 normalization for a 2-D C-contiguous float32 array.
///
/// Mirrors the C++ `normalize_l2_batch`, but raises `ValueError("Input must be
/// 2D")` (the runtime contract) instead of the C++ kernel's `RuntimeError`.
/// The parameter is a dynamic-dimension read-write view so this function — not
/// `PyO3`'s typed extractor — owns the `ndim` check and the exact exception
/// type and message. Each row is normalized in place; rows whose norm is
/// `<= 1e-10` are left unchanged; returns `None`.
#[pyfunction]
fn normalize_l2_batch(mut input: PyReadwriteArrayDyn<'_, f32>) -> PyResult<()> {
    let shape = input.shape();
    if shape.len() != 2 {
        return Err(PyValueError::new_err("Input must be 2D"));
    }
    let cols = shape[1];
    let slice = input.as_slice_mut().map_err(|_| {
        // A non-contiguous array cannot be mutated in place as a flat buffer.
        // The embedding pipeline always passes C-contiguous arrays
        // (np.vstack output), so this path is defensive only.
        PyValueError::new_err("normalize_l2_batch requires a C-contiguous 2D float32 array")
    })?;
    normalize_l2_batch_buffer(slice, cols);
    Ok(())
}

/// The Python module definition. The module name (`l2norm`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`l2norm.so`) imports as
/// `extensions.l2norm` once it is staged on `PYTHONPATH` under `extensions/`.
#[pymodule]
fn l2norm(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(normalize_l2, m)?)?;
    m.add_function(wrap_pyfunction!(normalize_l2_batch, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    // The exact-comparison assertions below check that sub-threshold / zero /
    // no-op rows are left bit-identical (the `<= 1e-10` guard must not touch
    // them at all). A strict `==` is the correct assertion there — an epsilon
    // would hide a regression that nudged an "unchanged" value. Allow clippy's
    // pedantic `float_cmp` for these intentional exact cases.
    #![allow(clippy::float_cmp)]

    use super::{normalize_l2_batch_buffer, normalize_l2_slice, MIN_NORM};

    /// Tolerance for float32 unit-norm assertions. IEEE 754-2019 single
    /// precision rounds unit-magnitude floats well within 1e-6.
    const TOL: f32 = 1e-6;

    fn l2_norm(values: &[f32]) -> f32 {
        values.iter().map(|v| v * v).sum::<f32>().sqrt()
    }

    // ── property-based test (proptest) over the pure core ────────────────────
    // Cases default to 50 (set below) and are raised via PROPTEST_CASES in CI.
    use proptest::prelude::*;

    proptest! {
        #![proptest_config(ProptestConfig { cases: 50, ..ProptestConfig::default() })]

        /// For ANY non-trivial vector, normalization yields unit L2 norm.
        ///
        /// Inputs are CONSTRUCTED, never filtered: 1..50 elements, each a
        /// magnitude in [0.1, 100] with either sign. That range guarantees the
        /// norm is always > MIN_NORM and never NaN/inf, so no generated value
        /// is ever discarded.
        #[test]
        fn prop_normalize_yields_unit_norm(
            vec in prop::collection::vec(
                (0.1f32..100.0f32, any::<bool>())
                    .prop_map(|(mag, neg)| if neg { -mag } else { mag }),
                1..50usize,
            )
        ) {
            let mut v = vec;
            normalize_l2_slice(&mut v);
            let norm = l2_norm(&v);
            // Tolerance accounts for f32 accumulation over up to 50 elements.
            prop_assert!(
                (norm - 1.0).abs() < 1e-3,
                "normalized norm should be ~1, got {norm}"
            );
        }
    }

    #[test]
    fn normalize_l2_slice_makes_unit_norm() {
        let mut v = [3.0_f32, 4.0];
        normalize_l2_slice(&mut v);
        // 3-4-5 triangle: norm 5 -> [0.6, 0.8].
        assert!((v[0] - 0.6).abs() < TOL, "got {v:?}");
        assert!((v[1] - 0.8).abs() < TOL, "got {v:?}");
        assert!((l2_norm(&v) - 1.0).abs() < TOL);
    }

    #[test]
    fn normalize_l2_slice_general_vector_has_unit_norm() {
        let mut v = [1.0_f32, -2.0, 2.0, 4.0, -1.5];
        normalize_l2_slice(&mut v);
        assert!((l2_norm(&v) - 1.0).abs() < TOL, "norm was {}", l2_norm(&v));
    }

    #[test]
    fn normalize_l2_slice_leaves_tiny_vector_unchanged() {
        // Norm is far below 1e-10, so the row must pass through untouched.
        let original = [1e-12_f32, 1e-12];
        let mut v = original;
        normalize_l2_slice(&mut v);
        assert_eq!(v, original, "sub-threshold vector must be left unchanged");
    }

    #[test]
    fn normalize_l2_slice_leaves_exact_zero_unchanged() {
        let mut v = [0.0_f32, 0.0, 0.0];
        normalize_l2_slice(&mut v);
        assert_eq!(v, [0.0, 0.0, 0.0]);
    }

    #[test]
    fn normalize_l2_slice_empty_is_noop() {
        let mut v: [f32; 0] = [];
        normalize_l2_slice(&mut v);
        assert!(v.is_empty());
    }

    #[test]
    fn min_norm_matches_cpp_threshold() {
        // The guard constant must equal the C++ kernel's 1e-10F.
        assert_eq!(MIN_NORM, 1e-10_f32);
    }

    #[test]
    fn normalize_l2_slice_at_exact_threshold_is_left_unchanged() {
        // A single element equal to MIN_NORM has norm exactly MIN_NORM, so the
        // strict `norm > MIN_NORM` guard must SKIP normalization (leave it as
        // is). This pins the boundary to `>`: a `>=` guard would normalize the
        // value to 1.0 instead, so this test kills the `> -> >=` mutant.
        let mut v = [MIN_NORM];
        normalize_l2_slice(&mut v);
        assert_eq!(
            v,
            [MIN_NORM],
            "value at the exact threshold must be unchanged"
        );
    }

    #[test]
    fn batch_normalizes_each_row_independently() {
        // Row 0 = [3,4] (norm 5), row 1 = [0,5] (norm 5).
        let mut buf = [3.0_f32, 4.0, 0.0, 5.0];
        normalize_l2_batch_buffer(&mut buf, 2);
        assert!((buf[0] - 0.6).abs() < TOL);
        assert!((buf[1] - 0.8).abs() < TOL);
        assert!((buf[2] - 0.0).abs() < TOL);
        assert!((buf[3] - 1.0).abs() < TOL);
    }

    #[test]
    fn batch_leaves_subthreshold_row_unchanged_but_normalizes_others() {
        // Row 0 is sub-threshold (must be untouched); row 1 is normal.
        let mut buf = [1e-12_f32, 1e-12, 6.0, 8.0];
        normalize_l2_batch_buffer(&mut buf, 2);
        assert_eq!(buf[0], 1e-12, "sub-threshold row 0 element 0 changed");
        assert_eq!(buf[1], 1e-12, "sub-threshold row 0 element 1 changed");
        assert!((buf[2] - 0.6).abs() < TOL);
        assert!((buf[3] - 0.8).abs() < TOL);
    }

    #[test]
    fn batch_zero_cols_is_noop() {
        let mut buf = [1.0_f32, 2.0];
        normalize_l2_batch_buffer(&mut buf, 0);
        assert_eq!(buf, [1.0, 2.0]);
    }

    #[test]
    fn batch_empty_is_noop() {
        let mut buf: [f32; 0] = [];
        normalize_l2_batch_buffer(&mut buf, 4);
        assert!(buf.is_empty());
    }
}
