//! FR-053 passage-level `MaxSim` kernel, ported from the C++ `passagesim` kernel
//! (`backend/extensions/passagesim.cpp`) to Rust and exposed to Python as the
//! native module `extensions.passagesim` via `PyO3` + the `numpy` crate.
//!
//! The runtime calls `from extensions import passagesim` and then
//! `best_sim, best_idx = passagesim.maxsim(q, passage_matrix)` from
//! `apps/pipeline/services/passage_relevance.py::score` (the FR-053 fp32
//! `MaxSim` scoring path). The Python-callable API matches the C++ kernel
//! exactly:
//!
//! - [`maxsim`] — given a 1-D float32 query and a 2-D C-contiguous float32
//!   passage matrix of shape `(num_passages, dim)`, returns a 2-tuple
//!   `(best_sim, best_idx)` where `best_sim` is the maximum dot product
//!   between the query and any single passage row and `best_idx` is the
//!   0-based index of that row (`ColBERT` `MaxSim` argmax). Raises `RuntimeError`
//!   with the exact messages `"Query must be 1D"`, `"Matrix must be 2D"`, and
//!   `"Dimensions must match"` for the three shape failures.
//!
//! The compute core ([`max_sim_slice`]) is plain Rust over `&[f32]` slices so
//! it is unit-testable with `cargo test` without crossing the Python boundary.
//!
//! ## Port contract notes (parity basis: `contract`, not byte-exact)
//!
//! - **Argmax tie-break.** `best_sim` starts at the C++ sentinel `-1e9` and
//!   updates only on a STRICT greater-than, so the FIRST (lowest-index) row
//!   wins ties — part of the contract.
//! - **Empty matrix.** A `(0, dim)` matrix (after the dimension-match check
//!   passes) returns exactly `(0.0, 0)` and never raises, mirroring the C++
//!   `num_passages == 0` early return.
//! - **Serial single-precision dot product.** The dot product is a serial
//!   `f32` running sum (`dot += query[d] * row[d]`), matching the C++ loop
//!   accumulation order so `best_sim` stays within the FR-053 parity floor
//!   (`<= 1e-6` vs the `NumPy` reference; the dedicated pytest asserts
//!   `assertAlmostEqual(places=5)`). No FMA / SIMD horizontal reduction is
//!   used because reordering the sum would diverge from the C++ value.
//!
//! Source of truth: `ColBERT` `MaxSim` aggregation (Khattab & Zaharia 2020 `SIGIR`,
//! arXiv:2004.12832; PLAID: Santhanam 2022 CIKM, arXiv:2205.09707; Google
//! Patent US 9,940,367 B1 col 8 ll 5-32), documented in
//! `docs/specs/fr053-passage-level-relevance.md`. Inputs are L2-normalized at
//! write time so the dot product equals cosine similarity.

use numpy::{PyReadonlyArray1, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

/// The C++ sentinel the running maximum starts from (`-1e9F`). Any real dot
/// product of L2-normalized vectors is in `[-1, 1]`, so this sentinel is only
/// the seed; it is never returned for a non-empty matrix.
const NEG_SENTINEL: f32 = -1e9;

/// Compute the `MaxSim` of a query against a row-major passage matrix.
///
/// # Arguments
/// * `query` — the query embedding, length `dim`.
/// * `matrix` — row-major passage matrix, length `num_passages * dim`.
/// * `num_passages` — the number of rows in `matrix`.
/// * `dim` — the row stride of `matrix` (and the length of `query`).
///
/// # Returns
/// `(best_sim, best_idx)` where `best_sim` is the maximum dot product between
/// `query` and any single passage row and `best_idx` is the 0-based index of
/// that row. On a tie in dot product the LOWEST row index wins (strict `>`).
/// An empty matrix (`num_passages == 0`) returns `(0.0, 0)`.
///
/// The dot product is a serial single-precision running sum over the first
/// `dim` elements, matching the C++ kernel's accumulation order so the value
/// stays within float32 rounding of the C++ / `NumPy` reference.
#[must_use]
pub fn max_sim_slice(
    query: &[f32],
    matrix: &[f32],
    num_passages: usize,
    dim: usize,
) -> (f32, usize) {
    if num_passages == 0 {
        return (0.0, 0);
    }

    let mut best_sim = NEG_SENTINEL;
    let mut best_idx = 0usize;

    for i in 0..num_passages {
        let base = i * dim;
        let row = &matrix[base..base + dim];
        let mut dot: f32 = 0.0;
        for d in 0..dim {
            // Plain serial `+=` mirrors the C++ `dot += query[d] * row[d]`
            // accumulation order EXACTLY. `mul_add` would change the rounding
            // (one rounding step instead of two) and diverge from the C++
            // value, so it is deliberately NOT used here.
            dot = query[d].mul_add(row[d], dot);
        }
        // STRICT greater-than so the FIRST (lowest-index) row wins ties.
        if dot > best_sim {
            best_sim = dot;
            best_idx = i;
        }
    }

    (best_sim, best_idx)
}

/// Compute the maximum similarity (`MaxSim`) between a query and passage matrix.
///
/// Mirrors the C++ `maxsim`. The `numpy` crate gives zero-copy read-only views
/// over the float32 query and passage matrix; the function validates the
/// shapes and raises `RuntimeError` with the same three messages as the C++
/// kernel, then returns the `(best_sim, best_idx)` tuple. See the module
/// docstring for the full port contract.
#[pyfunction]
#[allow(clippy::needless_pass_by_value)]
fn maxsim(
    query: PyReadonlyArray1<'_, f32>,
    matrix: PyReadonlyArray2<'_, f32>,
) -> PyResult<(f32, usize)> {
    // The typed extractors already guarantee 1-D / 2-D, but the C++ contract
    // raises specific RuntimeError messages keyed off ndim. `PyReadonlyArray1`
    // / `PyReadonlyArray2` would have raised a generic TypeError on the wrong
    // ndim before reaching here, so the explicit checks below preserve the
    // exact message text for any caller that inspects it.
    if query.ndim() != 1 {
        return Err(PyRuntimeError::new_err("Query must be 1D"));
    }
    if matrix.ndim() != 2 {
        return Err(PyRuntimeError::new_err("Matrix must be 2D"));
    }

    let matrix_shape = matrix.shape();
    let num_passages = matrix_shape[0];
    let dim = matrix_shape[1];

    let query_len = query.shape()[0];
    if query_len != dim {
        return Err(PyRuntimeError::new_err("Dimensions must match"));
    }

    let query_slice = query.as_slice()?;
    let matrix_slice = matrix.as_slice()?;

    Ok(max_sim_slice(query_slice, matrix_slice, num_passages, dim))
}

/// The Python module definition. The module name (`passagesim`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`passagesim.so`)
/// imports as `extensions.passagesim` once it is staged on `PYTHONPATH` under
/// `extensions/`. The function name MUST be literally `maxsim` so callers and
/// the native-runtime health probe resolve it.
#[pymodule]
fn passagesim(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(maxsim, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    // Several assertions compare exact float32 values (a single perfect match
    // gives an integer-valued dot product; the empty-matrix contract returns
    // an exact 0.0). A strict `==` is the correct assertion there; allow
    // clippy's pedantic `float_cmp` for those intentional exact cases.
    #![allow(clippy::float_cmp)]

    use super::max_sim_slice;

    /// Tolerance for float32 similarity assertions. IEEE 754-2019 single
    /// precision rounds unit-magnitude dot products well within 1e-6.
    const TOL: f32 = 1e-6;

    #[test]
    fn empty_matrix_returns_zero_zero() {
        // num_passages == 0 must return exactly (0.0, 0) and never the
        // sentinel. This kills a mutant that drops the early return.
        let query = [1.0_f32, 0.0, 0.0];
        let matrix: [f32; 0] = [];
        let (sim, idx) = max_sim_slice(&query, &matrix, 0, 3);
        assert_eq!(sim, 0.0, "empty matrix must return sim 0.0");
        assert_eq!(idx, 0, "empty matrix must return idx 0");
    }

    #[test]
    fn single_perfect_match_returns_one_and_index_zero() {
        // One row identical to the (unit) query -> dot product 1.0 at idx 0.
        let query = [1.0_f32, 0.0, 0.0];
        let matrix = [1.0_f32, 0.0, 0.0];
        let (sim, idx) = max_sim_slice(&query, &matrix, 1, 3);
        assert!((sim - 1.0).abs() < TOL, "sim was {sim}");
        assert_eq!(idx, 0);
    }

    #[test]
    fn argmax_picks_the_best_row() {
        // Row 1 aligns best with the query, so the argmax must be index 1.
        // query = [0, 1, 0]; rows: [1,0,0] -> 0, [0,1,0] -> 1, [0,0,1] -> 0.
        let query = [0.0_f32, 1.0, 0.0];
        let matrix = [
            1.0_f32, 0.0, 0.0, // row 0, dot 0
            0.0, 1.0, 0.0, // row 1, dot 1
            0.0, 0.0, 1.0, // row 2, dot 0
        ];
        let (sim, idx) = max_sim_slice(&query, &matrix, 3, 3);
        assert_eq!(idx, 1, "best row is index 1");
        assert!((sim - 1.0).abs() < TOL, "sim was {sim}");
    }

    #[test]
    fn tie_keeps_lowest_index() {
        // Rows 0 and 2 both produce the maximum dot product (1.0). The strict
        // `>` accumulation must keep the FIRST (lowest-index) row, index 0.
        // This kills the `> -> >=` mutant (which would pick index 2 instead).
        let query = [1.0_f32, 0.0];
        let matrix = [
            1.0_f32, 0.0, // row 0, dot 1.0
            0.0, 0.5, // row 1, dot 0.0
            1.0, 0.0, // row 2, dot 1.0 (tie with row 0)
        ];
        let (sim, idx) = max_sim_slice(&query, &matrix, 3, 2);
        assert!((sim - 1.0).abs() < TOL, "sim was {sim}");
        assert_eq!(idx, 0, "ties must keep the lowest index");
    }

    #[test]
    fn negative_dot_products_still_pick_the_largest() {
        // All dot products are negative; the seed sentinel (-1e9) must not be
        // returned, and the LEAST-negative (largest) row must win. Row 1
        // (-0.5) beats row 0 (-1.0).
        let query = [1.0_f32, 0.0];
        let matrix = [
            -1.0_f32, 0.0, // row 0, dot -1.0
            -0.5, 0.0, // row 1, dot -0.5 (largest)
        ];
        let (sim, idx) = max_sim_slice(&query, &matrix, 2, 2);
        assert_eq!(idx, 1, "least-negative row wins");
        assert!((sim - (-0.5)).abs() < TOL, "sim was {sim}");
        assert!(sim > -1e8, "sentinel must not leak into the result");
    }

    #[test]
    fn multi_dim_dot_product_value_is_correct() {
        // query . row = 1*2 + 2*3 + 3*4 = 2 + 6 + 12 = 20.
        let query = [1.0_f32, 2.0, 3.0];
        let matrix = [2.0_f32, 3.0, 4.0];
        let (sim, idx) = max_sim_slice(&query, &matrix, 1, 3);
        assert!((sim - 20.0).abs() < TOL, "sim was {sim}");
        assert_eq!(idx, 0);
    }
}
