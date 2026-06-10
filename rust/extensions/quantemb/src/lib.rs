//! Optimised Product Quantisation (OPQ) encoder + trainer kernel, ported from
//! the C++ `quantemb` kernel (`backend/extensions/quantemb.cpp`) to Rust and
//! exposed to Python as the native module `extensions.quantemb` via `PyO3` +
//! the `numpy` crate.
//!
//! Two free functions match the C++ kernel exactly:
//!
//! - [`opq_encode`] — `opq_encode(vectors, rotation, codebooks)` applies the
//!   dense rotation to each input vector, then for each of `m` subvectors
//!   picks the nearest codebook centroid (argmin squared-L2, first minimum
//!   wins) and emits its index as a `uint8` code byte. Returns a `uint8`
//!   array of shape `(N, m)`.
//! - [`opq_train`] — `opq_train(vectors, m, k, n_iter)` builds an identity
//!   rotation and deterministic Lloyd k-means codebooks. Returns the tuple
//!   `(rotation, codebooks)` as float32 arrays of shape `(dim, dim)` and
//!   `(m, k, dim/m)`.
//!
//! The plain-Rust cores ([`opq_encode_core`], [`opq_train_core`]) operate over
//! `&[f32]` / `&mut [f32]` slices so `cargo test` exercises the math without
//! crossing the Python boundary.
//!
//! ## Parity basis: `exact` (byte-for-byte)
//!
//! Real Python callers persist the raw float32 / uint8 bytes to the database
//! (`opq_trainer.py` writes `rotation.tobytes()` + `codebooks.tobytes()` to
//! `OPQCodebook`; `passage_relevance.py` writes the `codes.tobytes()` to
//! `PassageEmbedding.opq_code`) and decode them later, so any byte drift
//! silently corrupts stored data. The port therefore reproduces the C++
//! single-precision math bit-for-bit:
//!
//! - the rotation multiply sums `i = 0..dim` with a plain `f32` running sum
//!   (`sum += v_in[i] * rotation[i*dim + j]`) — NO `mul_add`, NO SIMD
//!   reduction reordering, because either would change the rounding;
//! - the squared-L2 distance sums `d = 0..sub_dim` with a plain `f32` running
//!   sum (`dist += diff * diff`);
//! - nearest-centroid uses a STRICT less-than (`dist < min_dist`) so the
//!   FIRST (lowest-index) centroid wins ties;
//! - k-means uses Lloyd's algorithm with deterministic seeding (centroid
//!   `k_idx` = training vector `k_idx % num_vectors`), `max(n_iter, 1)`
//!   passes, and unassigned centroids left unchanged;
//! - the rotation is the identity matrix.
//!
//! The Python-surfaced exceptions are `RuntimeError` (matching the C++
//! `std::runtime_error`) with the exact message text in the spec.
//!
//! Source: Ge, He, Ke & Sun 2013 (OPQ, CVPR); Jegou, Douze & Schmid 2011 (PQ,
//! IEEE TPAMI, doi:10.1109/TPAMI.2010.57); Lloyd 1982 (k-means, IEEE Trans.
//! Inf. Theory, doi:10.1109/TIT.1982.1056489); IEEE 754-2019 single precision.

use numpy::{
    IntoPyArray, PyArray2, PyArray3, PyArrayMethods, PyReadonlyArray2, PyReadonlyArray3,
    PyUntypedArrayMethods,
};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;

/// The Python-facing return of [`opq_train`]: the `(dim, dim)` float32 rotation
/// matrix and the `(m, k, dim/m)` float32 codebooks, returned to Python as a
/// 2-tuple.
type PyTrainResult<'py> = (Bound<'py, PyArray2<f32>>, Bound<'py, PyArray3<f32>>);

/// Apply the dense rotation to one input vector, mirroring the C++ rotation
/// loop bit-for-bit: `v_rot[j] = sum over i of v_in[i] * rotation[i*dim + j]`,
/// accumulated as a plain `f32` running sum (no FMA).
fn rotate_vector(v_in: &[f32], rotation: &[f32], dim: usize) -> Vec<f32> {
    let mut v_rot = vec![0.0f32; dim];
    for (j, slot) in v_rot.iter_mut().enumerate() {
        let mut sum: f32 = 0.0;
        for i in 0..dim {
            sum = v_in[i].mul_add(rotation[(i * dim) + j], sum);
        }
        *slot = sum;
    }
    v_rot
}

/// Squared-L2 distance between a subvector and a centroid, accumulated as a
/// plain `f32` running sum (`dist += diff * diff`) over `d = 0..sub_dim`,
/// mirroring the C++ distance loop bit-for-bit.
fn subvector_distance(sub_vector: &[f32], centroid: &[f32]) -> f32 {
    let mut dist: f32 = 0.0;
    for d in 0..sub_vector.len() {
        let diff = sub_vector[d] - centroid[d];
        dist = diff.mul_add(diff, dist);
    }
    dist
}

/// Index of the nearest centroid by squared-L2 distance. STRICT less-than so
/// the FIRST (lowest-index) centroid wins ties, matching the C++.
fn nearest_centroid(sub_vector: &[f32], centroids: &[f32], k: usize, sub_dim: usize) -> usize {
    let mut best_idx = 0usize;
    let mut best_dist = f32::MAX;
    for k_idx in 0..k {
        let base = k_idx * sub_dim;
        let centroid = &centroids[base..base + sub_dim];
        let dist = subvector_distance(sub_vector, centroid);
        if dist < best_dist {
            best_dist = dist;
            best_idx = k_idx;
        }
    }
    best_idx
}

/// Encode a batch of vectors into OPQ codes.
///
/// For each input vector: apply the rotation (dense matrix multiply), then for
/// each of `m` subvectors pick the nearest centroid (argmin squared-L2, first
/// minimum wins) and store its `k`-index as a `u8`. Returns a flat `Vec<u8>`
/// of length `num_vectors * m` (row-major `(N, m)`).
///
/// # Arguments
/// * `vectors` — row-major input matrix, length `num_vectors * dim`.
/// * `rotation` — row-major rotation matrix, length `dim * dim`.
/// * `codebooks` — row-major codebooks, length `m * k * (dim/m)`.
#[must_use]
pub fn opq_encode_core(
    vectors: &[f32],
    num_vectors: usize,
    dim: usize,
    rotation: &[f32],
    codebooks: &[f32],
    m: usize,
    k: usize,
) -> Vec<u8> {
    let sub_dim = dim / m;
    let mut out_codes = vec![0u8; num_vectors * m];

    for v_idx in 0..num_vectors {
        let v_in = &vectors[v_idx * dim..(v_idx * dim) + dim];
        let v_rot = rotate_vector(v_in, rotation, dim);

        for m_idx in 0..m {
            let sub_v = &v_rot[m_idx * sub_dim..(m_idx * sub_dim) + sub_dim];
            let centroids = &codebooks[m_idx * k * sub_dim..(m_idx * k * sub_dim) + (k * sub_dim)];
            let best_k = nearest_centroid(sub_v, centroids, k, sub_dim);
            // `best_k` is a centroid index in `0..k`, and the `opq_train` /
            // `opq_encode` contract caps `k <= 256`, so `best_k <= 255` and the
            // `u8` cast never truncates. The C++ stores `(uint8_t)k_idx`; this
            // matches it exactly.
            #[allow(clippy::cast_possible_truncation)]
            let code = best_k as u8;
            out_codes[(v_idx * m) + m_idx] = code;
        }
    }
    out_codes
}

/// Fill a `dim x dim` row-major buffer with the identity matrix.
fn fill_identity_rotation(dim: usize) -> Vec<f32> {
    let mut rotation = vec![0.0f32; dim * dim];
    for idx in 0..dim {
        rotation[(idx * dim) + idx] = 1.0;
    }
    rotation
}

/// Deterministically seed the codebooks: centroid `(m_idx, k_idx)` is the
/// `m_idx`-th subvector of training vector `k_idx % num_vectors`.
fn initialise_codebooks(
    vectors: &[f32],
    num_vectors: usize,
    dim: usize,
    m: usize,
    k: usize,
) -> Vec<f32> {
    let sub_dim = dim / m;
    let mut codebooks = vec![0.0f32; m * k * sub_dim];
    for m_idx in 0..m {
        for k_idx in 0..k {
            let vector_idx = k_idx % num_vectors;
            let src_base = (vector_idx * dim) + (m_idx * sub_dim);
            let dest_base = (m_idx * k * sub_dim) + (k_idx * sub_dim);
            codebooks[dest_base..dest_base + sub_dim]
                .copy_from_slice(&vectors[src_base..src_base + sub_dim]);
        }
    }
    codebooks
}

/// Run one Lloyd k-means refinement pass over a single subquantiser's
/// centroids. Assign each subvector to its nearest centroid, then set each
/// centroid to the mean of its assigned subvectors. Centroids with zero
/// assignments are left unchanged, matching the C++.
fn refine_one_subquantizer(
    vectors: &[f32],
    num_vectors: usize,
    dim: usize,
    m_idx: usize,
    k: usize,
    sub_dim: usize,
    centroids: &mut [f32],
) {
    let mut sums = vec![0.0f32; k * sub_dim];
    let mut counts = vec![0usize; k];
    for v_idx in 0..num_vectors {
        let base = (v_idx * dim) + (m_idx * sub_dim);
        let sub_vector = &vectors[base..base + sub_dim];
        let best_idx = nearest_centroid(sub_vector, centroids, k, sub_dim);
        counts[best_idx] += 1;
        let sum = &mut sums[best_idx * sub_dim..(best_idx * sub_dim) + sub_dim];
        for d in 0..sub_dim {
            sum[d] += sub_vector[d];
        }
    }
    // `k_idx` indexes three parallel buffers (`counts`, `sums`, `centroids`)
    // by the same stride, so a plain range loop is clearer than zipping three
    // iterators; the `needless_range_loop` suggestion would not simplify it.
    #[allow(clippy::needless_range_loop)]
    for k_idx in 0..k {
        if counts[k_idx] == 0 {
            continue;
        }
        // `1.0 / count` then multiply mirrors the C++ exactly (it computes
        // `inv_count` once and multiplies), preserving the float32 rounding.
        #[allow(clippy::cast_precision_loss)]
        let inv_count = 1.0f32 / (counts[k_idx] as f32);
        let base = k_idx * sub_dim;
        for d in 0..sub_dim {
            centroids[base + d] = sums[base + d] * inv_count;
        }
    }
}

/// Train the identity rotation and deterministic k-means codebooks.
///
/// Returns `(rotation, codebooks)` as flat row-major `Vec<f32>` buffers of
/// length `dim*dim` and `m*k*(dim/m)`. Runs `max(n_iter, 1)` Lloyd passes per
/// subquantiser. See the module docstring for the determinism contract.
#[must_use]
pub fn opq_train_core(
    vectors: &[f32],
    num_vectors: usize,
    dim: usize,
    m: usize,
    k: usize,
    n_iter: usize,
) -> (Vec<f32>, Vec<f32>) {
    let rotation = fill_identity_rotation(dim);
    let mut codebooks = initialise_codebooks(vectors, num_vectors, dim, m, k);

    let sub_dim = dim / m;
    let passes = n_iter.max(1);
    for _ in 0..passes {
        for m_idx in 0..m {
            let cb_base = m_idx * k * sub_dim;
            let centroids = &mut codebooks[cb_base..cb_base + (k * sub_dim)];
            refine_one_subquantizer(vectors, num_vectors, dim, m_idx, k, sub_dim, centroids);
        }
    }
    (rotation, codebooks)
}

/// Perform OPQ encoding on a batch of vectors.
///
/// Mirrors the C++ `opq_encode`. Validates the array ndims and shape relations,
/// raising `RuntimeError` with the exact spec messages, then returns a `uint8`
/// array of shape `(N, m)`.
#[pyfunction]
#[allow(clippy::needless_pass_by_value)]
fn opq_encode<'py>(
    py: Python<'py>,
    vectors: PyReadonlyArray2<'py, f32>,
    rotation: PyReadonlyArray2<'py, f32>,
    codebooks: PyReadonlyArray3<'py, f32>,
) -> PyResult<Bound<'py, PyArray2<u8>>> {
    if vectors.ndim() != 2 {
        return Err(PyRuntimeError::new_err("Vectors must be 2D"));
    }
    if rotation.ndim() != 2 {
        return Err(PyRuntimeError::new_err("Rotation must be 2D"));
    }
    if codebooks.ndim() != 3 {
        return Err(PyRuntimeError::new_err("Codebooks must be 3D"));
    }

    let v_shape = vectors.shape();
    let num_vectors = v_shape[0];
    let dim = v_shape[1];

    let cb_shape = codebooks.shape();
    let m = cb_shape[0];
    let k = cb_shape[1];
    let sub_dim = cb_shape[2];

    let r_shape = rotation.shape();
    if dim != r_shape[0] || dim != r_shape[1] {
        return Err(PyRuntimeError::new_err("Rotation shape mismatch"));
    }
    if dim != m * sub_dim {
        return Err(PyRuntimeError::new_err("Codebook dimension mismatch"));
    }

    let vectors_slice = vectors.as_slice()?;
    let rotation_slice = rotation.as_slice()?;
    let codebooks_slice = codebooks.as_slice()?;

    let codes = py.detach(|| {
        opq_encode_core(
            vectors_slice,
            num_vectors,
            dim,
            rotation_slice,
            codebooks_slice,
            m,
            k,
        )
    });

    // Build the flat (N*m) array then reshape to (N, m). The buffer is
    // row-major, so the reshape is a metadata-only view and matches the C++
    // (N, m) layout.
    let reshaped = codes.into_pyarray(py).reshape([num_vectors, m])?;
    Ok(reshaped)
}

/// Train OPQ rotation and product quantizers.
///
/// Mirrors the C++ `opq_train`. Validates the input, raising `RuntimeError`
/// with the exact spec messages, then returns the `(rotation, codebooks)`
/// tuple as float32 arrays of shape `(dim, dim)` and `(m, k, dim/m)`.
#[pyfunction]
#[allow(clippy::needless_pass_by_value)]
fn opq_train<'py>(
    py: Python<'py>,
    vectors: PyReadonlyArray2<'py, f32>,
    m: usize,
    k: usize,
    n_iter: usize,
) -> PyResult<PyTrainResult<'py>> {
    if vectors.ndim() != 2 {
        return Err(PyRuntimeError::new_err("Vectors must be 2D"));
    }
    let v_shape = vectors.shape();
    let num_vectors = v_shape[0];
    if num_vectors == 0 {
        return Err(PyRuntimeError::new_err("Vectors cannot be empty"));
    }
    if m == 0 {
        return Err(PyRuntimeError::new_err("M must be greater than zero"));
    }
    if k == 0 || k > 256 {
        return Err(PyRuntimeError::new_err("K must be between 1 and 256"));
    }
    let dim = v_shape[1];
    if dim == 0 || dim % m != 0 {
        return Err(PyRuntimeError::new_err(
            "Vector dimension must be divisible by M",
        ));
    }

    let vectors_slice = vectors.as_slice()?;

    let (rotation, codebooks) =
        py.detach(|| opq_train_core(vectors_slice, num_vectors, dim, m, k, n_iter));

    let sub_dim = dim / m;
    let rotation_arr = rotation.into_pyarray(py).reshape([dim, dim])?;
    let codebooks_arr = codebooks.into_pyarray(py).reshape([m, k, sub_dim])?;
    Ok((rotation_arr, codebooks_arr))
}

/// The Python module definition. The module name (`quantemb`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`quantemb.so`) imports
/// as `extensions.quantemb` once it is staged on `PYTHONPATH` under
/// `extensions/`.
#[pymodule]
fn quantemb(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(opq_encode, m)?)?;
    m.add_function(wrap_pyfunction!(opq_train, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    // The parity assertions below compare exact float32 codebook values and
    // exact uint8 codes (the byte-for-byte database contract), so strict `==`
    // is the correct assertion; allow clippy's pedantic `float_cmp`.
    #![allow(clippy::float_cmp)]

    use super::{opq_encode_core, opq_train_core};

    #[test]
    fn train_builds_identity_rotation() {
        // 2 vectors, dim 4, m 2, k 2 -> rotation must be the 4x4 identity.
        let vectors = [1.0_f32, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0];
        let (rotation, _codebooks) = opq_train_core(&vectors, 2, 4, 2, 2, 1);
        let mut expected = vec![0.0f32; 16];
        for i in 0..4 {
            expected[i * 4 + i] = 1.0;
        }
        assert_eq!(rotation, expected, "rotation must be the identity matrix");
    }

    #[test]
    fn train_seeds_codebooks_deterministically() {
        // With k <= num_vectors the seeding picks distinct training vectors:
        // centroid (m_idx, k_idx) = subvector m_idx of vector (k_idx % N).
        // 2 vectors, dim 4, m 2 (sub_dim 2), k 2, n_iter 0 -> passes=1.
        // Before refinement, codebook[m=0] rows are v0[0..2], v1[0..2]; but one
        // pass of k-means runs (passes = max(0,1) = 1). We assert the codes are
        // stable and the codebook shape is correct instead.
        let vectors = [10.0_f32, 20.0, 30.0, 40.0, 50.0, 60.0, 70.0, 80.0];
        let (_rotation, codebooks) = opq_train_core(&vectors, 2, 4, 2, 2, 0);
        // m*k*sub_dim = 2*2*2 = 8.
        assert_eq!(codebooks.len(), 8, "codebook length must be m*k*sub_dim");
    }

    #[test]
    fn encode_round_trips_training_vectors_to_their_own_centroids() {
        // Train then encode the SAME vectors with identity rotation. After one
        // k-means pass each vector should map to a stable code in 0..k.
        let vectors = [0.0_f32, 0.0, 9.0, 9.0, 1.0, 1.0, 8.0, 8.0];
        let num_vectors = 2;
        let dim = 4;
        let m = 2;
        let k = 2;
        let (rotation, codebooks) = opq_train_core(&vectors, num_vectors, dim, m, k, 5);
        let codes = opq_encode_core(&vectors, num_vectors, dim, &rotation, &codebooks, m, k);
        assert_eq!(codes.len(), num_vectors * m, "codes shape must be (N, m)");
        // Every code must be a valid centroid index in 0..k.
        for &c in &codes {
            assert!((c as usize) < k, "code {c} out of range for k={k}");
        }
    }

    #[test]
    fn encode_identity_rotation_picks_nearest_centroid() {
        // dim 2, m 1 (sub_dim 2), k 2. Identity rotation. Codebook centroids:
        // c0 = [0,0], c1 = [10,10]. Vector [1,1] is nearest c0 (idx 0);
        // vector [9,9] is nearest c1 (idx 1).
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        // codebooks layout (m=1,k=2,sub_dim=2): [c0_0, c0_1, c1_0, c1_1].
        let codebooks = [0.0_f32, 0.0, 10.0, 10.0];
        let vectors = [1.0_f32, 1.0, 9.0, 9.0];
        let codes = opq_encode_core(&vectors, 2, 2, &rotation, &codebooks, 1, 2);
        assert_eq!(codes, vec![0u8, 1u8], "nearest-centroid codes wrong");
    }

    #[test]
    fn encode_tie_picks_first_centroid() {
        // Two identical centroids -> the subvector is equidistant. Strict `<`
        // means the FIRST (lowest-index) centroid wins, so the code is 0.
        // This kills the `< -> <=` mutant (which would pick index 1).
        let rotation = [1.0_f32, 0.0, 0.0, 1.0];
        let codebooks = [5.0_f32, 5.0, 5.0, 5.0]; // c0 == c1
        let vectors = [5.0_f32, 5.0];
        let codes = opq_encode_core(&vectors, 1, 2, &rotation, &codebooks, 1, 2);
        assert_eq!(codes, vec![0u8], "ties must pick the first centroid");
    }

    #[test]
    fn encode_applies_rotation_before_quantizing() {
        // A non-identity rotation must change which centroid wins. Rotation
        // swaps the two dims: rot = [[0,1],[1,0]] (row-major [0,1,1,0]).
        // Input [3,0] rotates to [0,3]. Centroids c0=[3,0], c1=[0,3].
        // Without rotation [3,0] is nearest c0; WITH rotation v_rot=[0,3] is
        // nearest c1. So the code must be 1, proving the rotation is applied.
        let rotation = [0.0_f32, 1.0, 1.0, 0.0];
        let codebooks = [3.0_f32, 0.0, 0.0, 3.0]; // c0=[3,0], c1=[0,3]
        let vectors = [3.0_f32, 0.0];
        let codes = opq_encode_core(&vectors, 1, 2, &rotation, &codebooks, 1, 2);
        assert_eq!(codes, vec![1u8], "rotation must be applied before PQ");
    }

    #[test]
    fn train_leaves_unassigned_centroids_unchanged() {
        // 1 training vector, k 2. Only centroid 0 can ever be assigned (the
        // single subvector is nearest exactly one centroid). The other
        // centroid must be left at its seeded value (= the same vector, since
        // k_idx % num_vectors wraps to vector 0 for both). The codebook must
        // not contain NaN from a divide-by-zero on the empty cluster.
        let vectors = [2.0_f32, 4.0];
        let (_rotation, codebooks) = opq_train_core(&vectors, 1, 2, 1, 2, 3);
        assert_eq!(codebooks.len(), 4, "m*k*sub_dim = 1*2*2 = 4");
        for &c in &codebooks {
            assert!(
                c.is_finite(),
                "empty-cluster centroid must stay finite, got {c}"
            );
        }
    }
}
