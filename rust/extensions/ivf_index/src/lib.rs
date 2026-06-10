//! Inverted File (IVF) + OPQ asymmetric-distance vector-search kernel, ported
//! from the C++ `ivf_index` kernel (`backend/extensions/ivf_index.cpp` plus
//! `include/ivf_index_core.h`) to Rust and exposed to Python as the native
//! module `extensions.ivf_index` via `PyO3` + the `numpy` crate.
//!
//! The module exports exactly two Python-callable functions, matching the C++
//! `PYBIND11_MODULE(ivf_index, ...)` surface (no classes):
//!
//! - [`ivf_search`] — IVF + OPQ asymmetric-distance search across the whole
//!   corpus. Finds the top-`nprobe` nearest centroids, walks their assigned
//!   members, scores each by asymmetric distance computation (ADC), and returns
//!   the global indices of the nearest neighbours ordered by ascending ADC
//!   distance (length `<= top_k`). This function has NO production Python
//!   caller; it exists for completeness and the native-runtime health probe.
//! - [`adc_score_destination`] — per-destination ADC scoring. Builds the
//!   per-query ADC lookup table once and scores each OPQ code row, returning
//!   `(best_index, best_cosine_sim)` for the closest passage. This is the ONLY
//!   function with a real production caller
//!   (`apps/pipeline/services/passage_relevance.py::_try_score_path_opq_adc`).
//!
//! The compute core ([`find_top_centroids`], [`build_adc_lut`],
//! [`adc_distance`], [`ivf_search_core`], [`adc_score_destination_core`]) is
//! plain Rust over slices so it is unit-testable with `cargo test` without
//! crossing the Python boundary, mirroring `ivf_index_core.h`.
//!
//! ## Port contract notes (parity basis: `contract`, not byte-exact)
//!
//! - **Squared-L2 distance** is accumulated as a serial single-precision
//!   (`f32`) running sum in ascending index order, using `mul_add` for the
//!   `diff * diff` term so clippy's `suboptimal_flops` is satisfied while
//!   keeping one rounding step (maps to a hardware FMA). The C++ used a plain
//!   `dist += diff * diff`; under the `contract` parity basis the last-ULP
//!   difference from FMA is allowed (the binding floor is `<= 1e-4` ADC
//!   distance and correct ranking, not byte-identical float output).
//! - **Query rotation** is `q_rot[j] = sum_i query[i] * rotation[i*dim + j]`
//!   (`q . R`, with `R` indexed row-major as `rotation[i*dim + j]`), exactly
//!   as the C++.
//! - **Degenerate geometry** (`m == 0` or `dim % m != 0`) zero-fills the LUT
//!   (no error), so every code scores `0.0`.
//! - **Out-of-range** centroid ids (`< 0` or `>= n_centroids`) and vector ids
//!   (`< 0` or `>= n_total`) are silently skipped, never an error.
//! - **`adc_score_destination` empty input**: `n_passages == 0` returns
//!   `(0, 0.0)` BEFORE any shape validation.
//! - **Tie behaviour**: `adc_score_destination` keeps the FIRST minimum (strict
//!   `<`). `ivf_search` sorts ascending by distance with no tie stabilisation,
//!   matching the C++ `std::sort`; equal-distance indices may appear in any
//!   relative order, so the binding contract is the SET plus ascending order.
//! - **Cosine back-projection**: `cos = clamp(1 - dist/2, 0, 1)`, exact for
//!   L2-normalised vectors since `||a-b||^2 = 2 - 2*cos`.
//!
//! Source of truth: Sivic and Zisserman 2003 ICCV
//! (`doi:10.1109/ICCV.2003.1238663`, inverted file); Jegou, Douze and Schmid
//! 2010 CVPR / 2011 IEEE TPAMI (`doi:10.1109/TPAMI.2010.57`, Product
//! Quantization + IVFADC asymmetric distance computation); Ge, He, Ke and Sun
//! 2013 CVPR (`doi:10.1109/CVPR.2013.379`, Optimized Product Quantization).

use numpy::PyUntypedArrayMethods;
use numpy::{IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArray2, PyReadonlyArray3};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

/// The result of [`find_top_centroids`]: the selected centroid ids and their
/// matching squared-L2 distances, index-aligned and equal length.
type Centroids = (Vec<i32>, Vec<f32>);

/// Squared-L2 distance between two equal-length `f32` slices, accumulated as a
/// serial single-precision running sum in ascending index order.
///
/// `mul_add(diff, diff, acc)` keeps a single rounding step for the
/// `diff * diff` term (maps to a hardware FMA) and satisfies clippy's
/// `suboptimal_flops`. The summation order matches the C++ kernel.
#[must_use]
fn squared_l2(a: &[f32], b: &[f32]) -> f32 {
    let n = a.len().min(b.len());
    let mut dist = 0.0_f32;
    for d in 0..n {
        let diff = a[d] - b[d];
        dist = diff.mul_add(diff, dist);
    }
    dist
}

/// Find the indices and squared-L2 distances of the top `nprobe` centroids
/// closest to `query`.
///
/// Mirrors `c_ivf_find_top_centroids`. Returns `(ids, dists)` sorted ascending
/// by distance, length `min(nprobe, n_centroids)`. The C++ used a non-stable
/// `std::partial_sort`; this port uses a stable-by-(distance, id) sort, which
/// returns the SAME SET of top-`nprobe` centroids in ascending-distance order
/// and only fixes the otherwise-implementation-defined order of distance ties.
///
/// # Arguments
/// * `query` — query vector, length `dim`.
/// * `centroids` — row-major centroid matrix, length `n_centroids * dim`.
/// * `n_centroids` — number of centroid rows.
/// * `dim` — vector dimension (row stride of `centroids`).
/// * `nprobe` — how many centroids to return.
#[must_use]
pub fn find_top_centroids(
    query: &[f32],
    centroids: &[f32],
    n_centroids: usize,
    dim: usize,
    nprobe: usize,
) -> Centroids {
    let mut scored: Vec<(f32, i32)> = Vec::with_capacity(n_centroids);
    for c in 0..n_centroids {
        let base = c * dim;
        let centroid = &centroids[base..base + dim];
        let dist = squared_l2(query, centroid);
        // `c` is a slice index far below `i32::MAX` on any real input; the
        // `unwrap_or` keeps the function panic-free for the unreachable
        // overflow case instead of an unchecked cast.
        let id = i32::try_from(c).unwrap_or(i32::MAX);
        scored.push((dist, id));
    }

    // Ascending by distance, ties broken by centroid id ascending for a
    // deterministic, reproducible order (the C++ partial_sort left ties
    // implementation-defined; allowed because the parity basis is `contract`).
    scored.sort_by(|a, b| {
        a.0.partial_cmp(&b.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.1.cmp(&b.1))
    });

    let k = nprobe.min(n_centroids);
    let mut ids = Vec::with_capacity(k);
    let mut dists = Vec::with_capacity(k);
    for &(dist, id) in scored.iter().take(k) {
        ids.push(id);
        dists.push(dist);
    }
    (ids, dists)
}

/// Build the per-query asymmetric-distance-computation (ADC) lookup table.
///
/// Mirrors `c_ivf_build_adc_lut`. Writes `m * k` floats into `out_lut`. On
/// degenerate geometry (`m == 0` or `dim % m != 0`) the LUT is zero-filled with
/// no error. Otherwise the query is rotated `q_rot = q . R` (with `R` indexed
/// `rotation[i*dim + j]`) and `LUT[m_idx*k + k_idx]` is the squared-L2 between
/// the `m_idx`-th sub-vector of `q_rot` and `codebook[m_idx, k_idx, :]`.
///
/// # Arguments
/// * `query` — query vector, length `dim`.
/// * `rotation` — row-major rotation matrix `R`, length `dim * dim`.
/// * `codebooks` — row-major OPQ sub-codebooks, length `m * k * sub_dim`.
/// * `dim`, `m`, `k` — geometry; `sub_dim = dim / m`.
/// * `out_lut` — caller-provided output buffer of length `m * k`.
pub fn build_adc_lut(
    query: &[f32],
    rotation: &[f32],
    codebooks: &[f32],
    dim: usize,
    m: usize,
    k: usize,
    out_lut: &mut [f32],
) {
    if m == 0 || dim % m != 0 {
        // Degenerate input: zero-fill so the caller gets a deterministic
        // "no preference" LUT instead of garbage, matching the C++.
        for v in out_lut.iter_mut() {
            *v = 0.0;
        }
        return;
    }
    let sub_dim = dim / m;

    // 1. Rotate the query: q_rot[j] = sum_i query[i] * rotation[i*dim + j].
    let mut q_rot = vec![0.0_f32; dim];
    for (j, slot) in q_rot.iter_mut().enumerate() {
        let mut sum = 0.0_f32;
        for i in 0..dim {
            sum = query[i].mul_add(rotation[i * dim + j], sum);
        }
        *slot = sum;
    }

    // 2. For each (m_idx, k_idx) compute squared-L2 between q_rot's m-th
    //    sub-vector and codebook[m_idx, k_idx, :].
    for m_idx in 0..m {
        let q_base = m_idx * sub_dim;
        let sub_q = &q_rot[q_base..q_base + sub_dim];
        for k_idx in 0..k {
            let cb_base = (m_idx * k * sub_dim) + (k_idx * sub_dim);
            let centroid = &codebooks[cb_base..cb_base + sub_dim];
            out_lut[(m_idx * k) + k_idx] = squared_l2(sub_q, centroid);
        }
    }
}

/// Compute the asymmetric squared-L2 distance for one OPQ-coded vector against
/// a precomputed LUT: `distance = sum_m LUT[m, code[m]]`.
///
/// Mirrors `c_ivf_adc_distance`. `code` has length `m`; `lut` has length
/// `m * k` row-major.
#[must_use]
pub fn adc_distance(code: &[u8], lut: &[f32], m: usize, k: usize) -> f32 {
    let mut total = 0.0_f32;
    for m_idx in 0..m {
        total += lut[(m_idx * k) + code[m_idx] as usize];
    }
    total
}

/// Orchestrate the full IVF + OPQ search over the corpus.
///
/// Mirrors the body of the C++ `ivf_search` after shape validation. Returns the
/// global vector indices of the nearest neighbours ordered ascending by ADC
/// distance, length `<= top_k`. Out-of-range centroid ids and vector ids are
/// skipped.
///
/// # Arguments
/// * `query` — query vector, length `dim`.
/// * `centroids` — row-major centroid matrix, length `n_centroids * dim`.
/// * `partition_member_lists` — for each centroid, the global vector indices
///   assigned to it (length `n_centroids`).
/// * `opq_codes` — row-major OPQ codes, length `n_total * m`.
/// * `rotation` — row-major rotation matrix, length `dim * dim`.
/// * `codebooks` — row-major OPQ sub-codebooks, length `m * k * sub_dim`.
/// * geometry: `dim`, `n_centroids`, `n_total`, `m`, `k`.
/// * `nprobe`, `top_k`.
#[must_use]
#[allow(clippy::too_many_arguments)]
pub fn ivf_search_core(
    query: &[f32],
    centroids: &[f32],
    partition_member_lists: &[Vec<i32>],
    opq_codes: &[u8],
    rotation: &[f32],
    codebooks: &[f32],
    dim: usize,
    n_centroids: usize,
    n_total: usize,
    m: usize,
    k: usize,
    nprobe: usize,
    top_k: usize,
) -> Vec<i32> {
    let (centroid_ids, _dists) = find_top_centroids(query, centroids, n_centroids, dim, nprobe);

    let mut lut = vec![0.0_f32; m * k];
    build_adc_lut(query, rotation, codebooks, dim, m, k, &mut lut);

    // Score every in-range member of every chosen partition. We collect all
    // (distance, vec_idx) pairs then keep the smallest `top_k` by ascending
    // distance — equivalent to the C++ bounded max-heap, but simpler and with
    // a deterministic tie order (vec_idx ascending) that the `contract` basis
    // permits.
    let mut scored: Vec<(f32, i32)> = Vec::new();
    for &centroid_id in &centroid_ids {
        let Ok(cid) = usize::try_from(centroid_id) else {
            continue;
        };
        if cid >= n_centroids {
            continue;
        }
        for &vec_idx in &partition_member_lists[cid] {
            let Ok(vid) = usize::try_from(vec_idx) else {
                continue;
            };
            if vid >= n_total {
                continue;
            }
            let base = vid * m;
            let code = &opq_codes[base..base + m];
            let dist = adc_distance(code, &lut, m, k);
            scored.push((dist, vec_idx));
        }
    }

    scored.sort_by(|a, b| {
        a.0.partial_cmp(&b.0)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.1.cmp(&b.1))
    });

    let out_count = top_k.min(scored.len());
    scored.iter().take(out_count).map(|&(_, idx)| idx).collect()
}

/// Score one destination's OPQ codes and return the closest passage.
///
/// Mirrors the body of the C++ `adc_score_destination` after the empty-input
/// early return and shape validation. Returns `(best_index, best_cosine_sim)`
/// where `best_index` is the FIRST passage row with the minimum ADC distance
/// (strict `<`, ties keep the earlier index) and
/// `best_cosine_sim = clamp(1 - dist/2, 0, 1)`.
///
/// # Arguments
/// * `query` — query vector, length `dim`.
/// * `opq_codes` — row-major OPQ codes, length `n_passages * m`.
/// * `rotation` — row-major rotation matrix, length `dim * dim`.
/// * `codebooks` — row-major OPQ sub-codebooks, length `m * k * sub_dim`.
/// * geometry: `dim`, `n_passages`, `m`, `k`.
#[must_use]
#[allow(clippy::too_many_arguments)]
pub fn adc_score_destination_core(
    query: &[f32],
    opq_codes: &[u8],
    rotation: &[f32],
    codebooks: &[f32],
    dim: usize,
    n_passages: usize,
    m: usize,
    k: usize,
) -> (i64, f32) {
    let mut lut = vec![0.0_f32; m * k];
    build_adc_lut(query, rotation, codebooks, dim, m, k, &mut lut);

    let mut best_idx: i64 = 0;
    let mut best_dist = 1e30_f32;
    for i in 0..n_passages {
        let base = i * m;
        let code = &opq_codes[base..base + m];
        let dist = adc_distance(code, &lut, m, k);
        if dist < best_dist {
            best_dist = dist;
            // `i < n_passages` is a slice index, far below `i64::MAX`.
            best_idx = i64::try_from(i).unwrap_or(i64::MAX);
        }
    }

    // Squared-L2 between two L2-normalised vectors a, b is ||a-b||^2 = 2 - 2cos,
    // so cos = 1 - dist/2; clamp to [0, 1] for numerical safety.
    let cosine_sim = best_dist.mul_add(-0.5, 1.0).clamp(0.0, 1.0);
    (best_idx, cosine_sim)
}

/// IVF + OPQ asymmetric-distance search. Returns top-k global indices ordered
/// ascending by ADC distance.
///
/// Mirrors the C++ `ivf_search`. Raises `RuntimeError` with the same messages
/// as the C++ on shape/geometry mismatch and on an out-of-range `nprobe` /
/// `top_k`.
#[pyfunction]
#[pyo3(signature = (query, centroids, partition_member_lists, opq_codes, rotation, codebooks, nprobe=16, top_k=100))]
#[allow(clippy::needless_pass_by_value, clippy::too_many_arguments)]
fn ivf_search<'py>(
    py: Python<'py>,
    query: PyReadonlyArray1<'py, f32>,
    centroids: PyReadonlyArray2<'py, f32>,
    partition_member_lists: Vec<Vec<i32>>,
    opq_codes: PyReadonlyArray2<'py, u8>,
    rotation: PyReadonlyArray2<'py, f32>,
    codebooks: PyReadonlyArray3<'py, f32>,
    nprobe: i64,
    top_k: i64,
) -> PyResult<Bound<'py, PyArray1<i32>>> {
    if query.ndim() != 1 {
        return Err(PyRuntimeError::new_err("query must be 1D"));
    }
    if centroids.ndim() != 2 {
        return Err(PyRuntimeError::new_err("centroids must be 2D"));
    }
    if opq_codes.ndim() != 2 {
        return Err(PyRuntimeError::new_err("opq_codes must be 2D"));
    }
    if rotation.ndim() != 2 {
        return Err(PyRuntimeError::new_err("rotation must be 2D"));
    }
    if codebooks.ndim() != 3 {
        return Err(PyRuntimeError::new_err(
            "codebooks must be 3D (m, k, sub_dim)",
        ));
    }

    let dim = query.shape()[0];
    let n_centroids = centroids.shape()[0];
    let n_total = opq_codes.shape()[0];
    let m = opq_codes.shape()[1];
    let k = codebooks.shape()[1];

    if centroids.shape()[1] != dim {
        return Err(PyRuntimeError::new_err(
            "centroids second dim must equal query dim",
        ));
    }
    if codebooks.shape()[0] != m {
        return Err(PyRuntimeError::new_err(
            "codebooks first dim (m) must equal opq_codes second dim",
        ));
    }
    if rotation.shape()[0] != dim || rotation.shape()[1] != dim {
        return Err(PyRuntimeError::new_err("rotation must be (dim, dim)"));
    }
    if partition_member_lists.len() != n_centroids {
        return Err(PyRuntimeError::new_err(
            "partition_member_lists length must equal n_centroids",
        ));
    }
    // `nprobe` must be in [1, n_centroids]. A value > i64 range of n_centroids
    // is impossible; compare against the usize bound after a sign check.
    if nprobe < 1 || usize::try_from(nprobe).map_or(true, |n| n > n_centroids) {
        return Err(PyRuntimeError::new_err(
            "nprobe must be in [1, n_centroids]",
        ));
    }
    if top_k < 1 {
        return Err(PyRuntimeError::new_err("top_k must be >= 1"));
    }

    let query_slice = query.as_slice()?;
    let centroids_slice = centroids.as_slice()?;
    let codes_slice = opq_codes.as_slice()?;
    let rotation_slice = rotation.as_slice()?;
    let codebooks_slice = codebooks.as_slice()?;

    // The bounds above guarantee these casts are in range.
    let nprobe_usize = usize::try_from(nprobe).unwrap_or(0);
    let top_k_usize = usize::try_from(top_k).unwrap_or(0);

    let results = py.detach(|| {
        ivf_search_core(
            query_slice,
            centroids_slice,
            &partition_member_lists,
            codes_slice,
            rotation_slice,
            codebooks_slice,
            dim,
            n_centroids,
            n_total,
            m,
            k,
            nprobe_usize,
            top_k_usize,
        )
    });

    Ok(results.into_pyarray(py))
}

/// Per-destination OPQ ADC scoring. Returns `(best_passage_index,
/// best_cosine_similarity)`.
///
/// Mirrors the C++ `adc_score_destination`, including the empty-input early
/// return `(0, 0.0)` BEFORE any shape validation. Used by FR-053
/// `passage_relevance.score()`.
#[pyfunction]
#[allow(clippy::needless_pass_by_value)]
fn adc_score_destination(
    py: Python<'_>,
    query: PyReadonlyArray1<'_, f32>,
    opq_codes: PyReadonlyArray2<'_, u8>,
    rotation: PyReadonlyArray2<'_, f32>,
    codebooks: PyReadonlyArray3<'_, f32>,
) -> PyResult<(i64, f32)> {
    if query.ndim() != 1 {
        return Err(PyRuntimeError::new_err("query must be 1D"));
    }
    if opq_codes.ndim() != 2 {
        return Err(PyRuntimeError::new_err("opq_codes must be 2D"));
    }

    let dim = query.shape()[0];
    let n_passages = opq_codes.shape()[0];
    let m = opq_codes.shape()[1];

    // Empty input early-return BEFORE rotation/codebook shape checks, matching
    // the C++ `if (n_passages == 0) return make_tuple(0, 0.0f);`.
    if n_passages == 0 {
        return Ok((0, 0.0));
    }

    if rotation.ndim() != 2 {
        return Err(PyRuntimeError::new_err("rotation must be 2D"));
    }
    if codebooks.ndim() != 3 {
        return Err(PyRuntimeError::new_err(
            "codebooks must be 3D (m, k, sub_dim)",
        ));
    }

    let k = codebooks.shape()[1];

    if codebooks.shape()[0] != m {
        return Err(PyRuntimeError::new_err(
            "codebooks first dim (m) must equal opq_codes second dim",
        ));
    }
    if rotation.shape()[0] != dim || rotation.shape()[1] != dim {
        return Err(PyRuntimeError::new_err("rotation must be (dim, dim)"));
    }

    let query_slice = query.as_slice()?;
    let codes_slice = opq_codes.as_slice()?;
    let rotation_slice = rotation.as_slice()?;
    let codebooks_slice = codebooks.as_slice()?;

    let result = py.detach(|| {
        adc_score_destination_core(
            query_slice,
            codes_slice,
            rotation_slice,
            codebooks_slice,
            dim,
            n_passages,
            m,
            k,
        )
    });

    Ok(result)
}

/// The Python module definition. The module name (`ivf_index`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`ivf_index.so`) imports
/// as `extensions.ivf_index` once it is staged on `PYTHONPATH` under
/// `extensions/`. Both `ivf_search` and `adc_score_destination` MUST be
/// registered so the production caller and the native-runtime health probe
/// (which checks the `ivf_search` attribute) keep working.
#[pymodule]
fn ivf_index(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(ivf_search, m)?)?;
    m.add_function(wrap_pyfunction!(adc_score_destination, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    // The test fixtures build deterministic small integer-valued floats via
    // `as f32` casts that stay in a tiny bounded range, so the precision lints
    // do not apply; exact float compares on those exact integer-valued scores
    // are intentional.
    #![allow(
        clippy::float_cmp,
        clippy::cast_precision_loss,
        clippy::cast_possible_truncation,
        clippy::cast_possible_wrap
    )]

    use super::{
        adc_distance, adc_score_destination_core, build_adc_lut, find_top_centroids,
        ivf_search_core, squared_l2,
    };

    #[test]
    fn squared_l2_basic() {
        let a = [1.0_f32, 2.0, 3.0];
        let b = [1.0_f32, 0.0, 0.0];
        // diffs: 0, 2, 3 -> 0 + 4 + 9 = 13.
        assert_eq!(squared_l2(&a, &b), 13.0);
    }

    #[test]
    fn squared_l2_truncates_to_shorter() {
        let a = [1.0_f32, 2.0, 100.0];
        let b = [1.0_f32, 0.0];
        // Only first 2 elements: 0 + 4 = 4; the 100.0 is ignored.
        assert_eq!(squared_l2(&a, &b), 4.0);
    }

    #[test]
    fn find_top_centroids_orders_ascending_and_truncates() {
        // 3 centroids, dim 2. query = [0,0]; centroid dists are the squared
        // norms: c0=[3,4]->25, c1=[1,0]->1, c2=[0,2]->4.
        let query = [0.0_f32, 0.0];
        let centroids = [3.0_f32, 4.0, 1.0, 0.0, 0.0, 2.0];
        let (ids, dists) = find_top_centroids(&query, &centroids, 3, 2, 2);
        assert_eq!(ids, vec![1, 2], "nearest two by squared-L2");
        assert_eq!(dists, vec![1.0, 4.0]);
    }

    #[test]
    fn find_top_centroids_nprobe_capped_at_n_centroids() {
        let query = [0.0_f32];
        let centroids = [2.0_f32, 5.0]; // 2 centroids, dim 1
        let (ids, _dists) = find_top_centroids(&query, &centroids, 2, 1, 100);
        assert_eq!(ids.len(), 2, "nprobe capped at n_centroids");
    }

    #[test]
    fn find_top_centroids_tie_break_id_ascending() {
        // Two centroids equidistant; lower id comes first.
        let query = [0.0_f32];
        let centroids = [3.0_f32, 3.0]; // both dist 9
        let (ids, dists) = find_top_centroids(&query, &centroids, 2, 1, 2);
        assert_eq!(ids, vec![0, 1]);
        assert_eq!(dists, vec![9.0, 9.0]);
    }

    #[test]
    fn build_adc_lut_degenerate_m_zero_zero_fills() {
        let query = [1.0_f32, 2.0];
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        let codebooks: [f32; 0] = [];
        let mut lut: Vec<f32> = Vec::new(); // m*k = 0
        build_adc_lut(&query, &rotation, &codebooks, 2, 0, 0, &mut lut);
        assert!(lut.is_empty());
    }

    #[test]
    fn build_adc_lut_degenerate_dim_not_divisible_zero_fills() {
        // dim=3, m=2 -> 3 % 2 != 0 -> zero-fill.
        let query = [1.0_f32, 2.0, 3.0];
        let rotation = vec![0.0_f32; 9];
        let codebooks = vec![1.0_f32; 4]; // arbitrary
        let mut lut = vec![7.0_f32; 4]; // m*k = 2*2
        build_adc_lut(&query, &rotation, &codebooks, 3, 2, 2, &mut lut);
        assert_eq!(
            lut,
            vec![0.0, 0.0, 0.0, 0.0],
            "degenerate geometry zero-fills"
        );
    }

    #[test]
    fn build_adc_lut_identity_rotation() {
        // dim=2, m=1, k=2, sub_dim=2. Identity rotation -> q_rot == query.
        // query = [1, 0]; codebooks: code0=[1,0] (dist 0), code1=[0,1] (dist 2).
        let query = [1.0_f32, 0.0];
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        let codebooks = [1.0_f32, 0.0, 0.0, 1.0];
        let mut lut = vec![0.0_f32; 2];
        build_adc_lut(&query, &rotation, &codebooks, 2, 1, 2, &mut lut);
        // LUT[0,0] = ||[1,0]-[1,0]||^2 = 0; LUT[0,1] = ||[1,0]-[0,1]||^2 = 2.
        assert_eq!(lut, vec![0.0, 2.0]);
    }

    #[test]
    fn build_adc_lut_uses_q_dot_r_indexing() {
        // Non-identity rotation to lock in the rotation[i*dim + j] convention
        // (q . R, NOT R . q). dim=2, m=1, k=1, sub_dim=2.
        // R = [[0,1],[1,0]] (swap). q=[2,3] -> q_rot[j] = sum_i q[i]*R[i*2+j].
        //   q_rot[0] = q[0]*R[0]+q[1]*R[2] = 2*0 + 3*1 = 3.
        //   q_rot[1] = q[0]*R[1]+q[1]*R[3] = 2*1 + 3*0 = 2.
        // codebook code0 = [3,2] -> dist 0.
        let query = [2.0_f32, 3.0];
        let rotation = [0.0_f32, 1.0, 1.0, 0.0];
        let codebooks = [3.0_f32, 2.0];
        let mut lut = vec![9.0_f32; 1];
        build_adc_lut(&query, &rotation, &codebooks, 2, 1, 1, &mut lut);
        assert_eq!(lut, vec![0.0], "q.R indexing rotates [2,3]->[3,2]");
    }

    #[test]
    fn adc_distance_sums_lut_by_code() {
        // m=2, k=3. lut row0 = [0.1, 0.2, 0.3], row1 = [1.0, 2.0, 3.0].
        let lut = [0.1_f32, 0.2, 0.3, 1.0, 2.0, 3.0];
        let code = [2_u8, 0]; // lut[0*3+2]=0.3, lut[1*3+0]=1.0
        let d = adc_distance(&code, &lut, 2, 3);
        assert!((d - 1.3).abs() < 1e-6);
    }

    #[test]
    fn adc_score_destination_empty_returns_zero_zero() {
        // n_passages == 0 returns (0, 0.0) before any other work.
        let query = [1.0_f32, 0.0];
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        let codebooks = [1.0_f32, 0.0, 0.0, 1.0];
        let (idx, sim) = adc_score_destination_core(&query, &[], &rotation, &codebooks, 2, 0, 1, 2);
        assert_eq!(idx, 0);
        assert_eq!(sim, 0.0);
    }

    #[test]
    fn adc_score_destination_first_minimum_wins() {
        // Two passages with identical distance; the FIRST (index 0) wins.
        // dim=2, m=1, k=2, sub_dim=2. Identity rotation. query=[1,0].
        // codebook code0=[1,0] (dist 0), code1=[0,1] (dist 2).
        // Both passages use code byte 0 -> both dist 0 -> first wins.
        let query = [1.0_f32, 0.0];
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        let codebooks = [1.0_f32, 0.0, 0.0, 1.0];
        let opq_codes = [0_u8, 0]; // 2 passages, m=1, both code 0
        let (idx, sim) =
            adc_score_destination_core(&query, &opq_codes, &rotation, &codebooks, 2, 2, 1, 2);
        assert_eq!(idx, 0, "first minimum wins on tie");
        // dist 0 -> cos = 1 - 0/2 = 1.
        assert_eq!(sim, 1.0);
    }

    #[test]
    fn adc_score_destination_picks_closest_and_back_projects_cosine() {
        // query=[1,0], identity rotation, codebook code0=[1,0] dist0, code1=[0,1] dist2.
        // passage 0 uses code1 (dist 2, cos = 1 - 1 = 0), passage 1 uses code0 (dist 0, cos 1).
        let query = [1.0_f32, 0.0];
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        let codebooks = [1.0_f32, 0.0, 0.0, 1.0];
        let opq_codes = [1_u8, 0]; // passage0->code1, passage1->code0
        let (idx, sim) =
            adc_score_destination_core(&query, &opq_codes, &rotation, &codebooks, 2, 2, 1, 2);
        assert_eq!(idx, 1, "passage 1 (code0, dist 0) is closest");
        assert_eq!(sim, 1.0);
    }

    #[test]
    fn adc_score_destination_clamps_cosine_to_zero() {
        // A large distance (>2) must clamp cosine to 0, never go negative.
        // query=[1,0], code1=[0,3] -> dist = ||[1,0]-[0,3]||^2 = 1+9 = 10.
        // cos = 1 - 10/2 = -4 -> clamp to 0.
        let query = [1.0_f32, 0.0];
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        let codebooks = [0.0_f32, 3.0]; // single code = [0,3]
        let opq_codes = [0_u8]; // 1 passage, code 0
        let (idx, sim) =
            adc_score_destination_core(&query, &opq_codes, &rotation, &codebooks, 2, 1, 1, 1);
        assert_eq!(idx, 0);
        assert_eq!(sim, 0.0, "negative cosine clamps to 0");
    }

    #[test]
    fn ivf_search_skips_out_of_range_ids() {
        // 2 centroids dim 1; query=[0]. centroids c0=[1] (dist1), c1=[0] (dist0).
        // nprobe 2 -> chosen ids [1, 0]. partition lists: c0 members [0, 99]
        // (99 out of range, n_total=2), c1 members [-1, 1] (-1 out of range).
        // m=1, k=1, sub_dim=1, identity rotation. codebook code0=[0].
        // q_rot = q = [0]; lut[0] = ||0 - 0||^2 = 0 -> all dists 0.
        let query = [0.0_f32];
        let centroids = [1.0_f32, 0.0];
        let partition_member_lists = vec![vec![0_i32, 99], vec![-1_i32, 1]];
        let opq_codes = [0_u8, 0]; // n_total=2, m=1
        let rotation = [1.0_f32];
        let codebooks = [0.0_f32]; // m=1,k=1,sub_dim=1
        let out = ivf_search_core(
            &query,
            &centroids,
            &partition_member_lists,
            &opq_codes,
            &rotation,
            &codebooks,
            1,  // dim
            2,  // n_centroids
            2,  // n_total
            1,  // m
            1,  // k
            2,  // nprobe
            10, // top_k
        );
        // Valid members across both partitions: vec 0 (from c0) and vec 1
        // (from c1); 99 and -1 skipped. All dist 0; tie-break vec_idx ascending.
        assert_eq!(out, vec![0, 1]);
    }

    #[test]
    fn ivf_search_top_k_bounds_result_length() {
        // 1 centroid dim 1; query=[0]. partition has 5 members 0..5.
        // All same dist 0. top_k=3 -> 3 results.
        let query = [0.0_f32];
        let centroids = [0.0_f32];
        let partition_member_lists = vec![vec![0_i32, 1, 2, 3, 4]];
        let opq_codes = vec![0_u8; 5]; // 5 passages, m=1
        let rotation = [1.0_f32];
        let codebooks = [0.0_f32];
        let out = ivf_search_core(
            &query,
            &centroids,
            &partition_member_lists,
            &opq_codes,
            &rotation,
            &codebooks,
            1,
            1,
            5,
            1,
            1,
            1,
            3,
        );
        assert_eq!(out.len(), 3, "result length bounded by top_k");
        assert_eq!(out, vec![0, 1, 2], "smallest tie-broken vec indices");
    }

    #[test]
    fn ivf_search_ranks_by_adc_distance() {
        // 1 centroid, dim 2, m 1, k 2, sub_dim 2. Identity rotation. query=[1,0].
        // codebook code0=[1,0] (dist0), code1=[0,1] (dist2).
        // 3 passages: p0 code1 (dist2), p1 code0 (dist0), p2 code1 (dist2).
        // top_k 3 -> ordered ascending by dist then vec_idx: p1(0), p0(2), p2(2).
        let query = [1.0_f32, 0.0];
        let centroids = [1.0_f32, 0.0];
        let partition_member_lists = vec![vec![0_i32, 1, 2]];
        let opq_codes = [1_u8, 0, 1]; // p0->code1, p1->code0, p2->code1
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        let codebooks = [1.0_f32, 0.0, 0.0, 1.0];
        let out = ivf_search_core(
            &query,
            &centroids,
            &partition_member_lists,
            &opq_codes,
            &rotation,
            &codebooks,
            2,
            1,
            3,
            1,
            2,
            1,
            3,
        );
        assert_eq!(
            out,
            vec![1, 0, 2],
            "closest first, ties by vec_idx ascending"
        );
    }

    #[test]
    fn ivf_search_many_vectors_parity_with_reference() {
        // 8 centroids, dim 8, m 4, k 16, sub_dim 2. Deterministic values.
        // Compare the kernel's top-10 set against an independent f64 brute-force
        // reference over the same chosen partitions.
        let dim = 8_usize;
        let m = 4_usize;
        let k = 16_usize;
        let sub_dim = dim / m;
        let n_centroids = 8_usize;
        let n_total = 200_usize;

        let query: Vec<f32> = (0..dim).map(|d| ((d * 3 % 7) as f32) - 3.0).collect();
        let centroids: Vec<f32> = (0..n_centroids * dim)
            .map(|i| (((i * 5) % 13) as f32) - 6.0)
            .collect();
        // Each vector assigned round-robin to a centroid partition.
        let mut partition_member_lists: Vec<Vec<i32>> = vec![Vec::new(); n_centroids];
        for v in 0..n_total {
            partition_member_lists[v % n_centroids].push(v as i32);
        }
        let opq_codes: Vec<u8> = (0..n_total * m).map(|i| ((i * 7) % k) as u8).collect();
        // Identity-ish rotation (true identity) so q_rot == query.
        let mut rotation = vec![0.0_f32; dim * dim];
        for d in 0..dim {
            rotation[d * dim + d] = 1.0;
        }
        let codebooks: Vec<f32> = (0..m * k * sub_dim)
            .map(|i| (((i * 11) % 17) as f32) - 8.0)
            .collect();

        let nprobe = 3_usize;
        let top_k = 10_usize;
        let out = ivf_search_core(
            &query,
            &centroids,
            &partition_member_lists,
            &opq_codes,
            &rotation,
            &codebooks,
            dim,
            n_centroids,
            n_total,
            m,
            k,
            nprobe,
            top_k,
        );
        assert_eq!(out.len(), top_k);

        // Independent reference: rebuild the LUT in f64 and brute-force the
        // chosen partitions, then take the smallest top_k by (dist, vec_idx).
        let (centroid_ids, _) = find_top_centroids(&query, &centroids, n_centroids, dim, nprobe);
        // f64 LUT.
        let mut q_rot = vec![0.0_f64; dim];
        for j in 0..dim {
            let mut s = 0.0_f64;
            for i in 0..dim {
                s += f64::from(query[i]) * f64::from(rotation[i * dim + j]);
            }
            q_rot[j] = s;
        }
        let mut lut64 = vec![0.0_f64; m * k];
        for mi in 0..m {
            for ki in 0..k {
                let mut d = 0.0_f64;
                for s in 0..sub_dim {
                    let diff = q_rot[mi * sub_dim + s]
                        - f64::from(codebooks[(mi * k * sub_dim) + (ki * sub_dim) + s]);
                    d += diff * diff;
                }
                lut64[mi * k + ki] = d;
            }
        }
        let mut ref_scored: Vec<(f64, i32)> = Vec::new();
        for &cid in &centroid_ids {
            let cid_u = usize::try_from(cid).unwrap_or(0);
            for &vid in &partition_member_lists[cid_u] {
                let mut d = 0.0_f64;
                let vid_u = usize::try_from(vid).unwrap_or(0);
                for mi in 0..m {
                    d += lut64[mi * k + usize::from(opq_codes[vid_u * m + mi])];
                }
                ref_scored.push((d, vid));
            }
        }
        ref_scored.sort_by(|a, b| {
            a.0.partial_cmp(&b.0)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(a.1.cmp(&b.1))
        });
        let ref_top: Vec<i32> = ref_scored.iter().take(top_k).map(|p| p.1).collect();
        assert_eq!(out, ref_top, "top-10 set/order must match f64 reference");
    }

    #[test]
    fn nan_query_does_not_panic() {
        // A NaN in the query yields NaN distances; partial_cmp returns None and
        // unwrap_or(Equal) keeps the sort total and panic-free.
        let query = [f32::NAN, 1.0];
        let centroids = [1.0_f32, 0.0, 0.0, 1.0];
        let (ids, _dists) = find_top_centroids(&query, &centroids, 2, 2, 2);
        assert_eq!(ids.len(), 2);
    }
}
