//! Weighted PageRank / personalized PageRank / HITS power-iteration hot-path
//! kernel, ported from the C++ `pagerank` kernel
//! (`backend/extensions/pagerank.cpp` plus `include/pagerank_core.h`) to Rust
//! and exposed to Python as the native module `extensions.pagerank` via `PyO3`
//! and the `numpy` crate.
//!
//! Three module-level functions, each running ONE iteration step over a weighted
//! CSR adjacency matrix (row = target, col = source); the Python callers drive
//! the convergence loop:
//!
//! - `pagerank_step(indptr, indices, data, ranks, dangling_mask, damping,
//!   node_count) -> (np.ndarray[f64], float)` (Page, Brin, Motwani & Winograd
//!   1999).
//! - `personalized_pagerank_step(..., personalization, damping, node_count) ->
//!   (np.ndarray[f64], float)` (Haveliwala 2002, doi:10.1145/511446.511513).
//! - `hits_step(indptr, indices, data, authority, hub, node_count) ->
//!   (np.ndarray[f64], np.ndarray[f64])` (Kleinberg 1999,
//!   doi:10.1145/324133.324140).
//!
//! `damping` is the teleport probability (textbook `1 - alpha`).
//!
//! ## Parity (port note)
//!
//! Parity is EXACT. Real ranking callers persist `march_2026_pagerank_score` to
//! the database and feed downstream signals, and dedicated parity tests compare
//! against line-for-line Python references. Every operation is a deterministic
//! serial double-precision accumulation with no hashing, RNG, `f32`, or
//! threading. This port uses plain sequential `f64 +=` (NOT `mul_add`/FMA, NOT
//! parallel/pairwise reduction) so the per-row summation order matches the C++
//! `+=` order bit-for-bit. The two renormalisation differences are reproduced
//! exactly: `pagerank_step` divides by the total mass unconditionally;
//! `personalized_pagerank_step` divides only when the total is positive;
//! `hits_step` never normalises and zeroes both output buffers first.

// "PageRank" / "HITS" are proper nouns that appear throughout the prose docs;
// backtick-quoting every occurrence would hurt readability, so the markdown lint
// is allowed crate-wide.
#![allow(clippy::doc_markdown)]

use numpy::{IntoPyArray, PyReadonlyArray1};
use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

/// One weighted PageRank step over CSR slices. Returns `(next_ranks, delta)`.
///
/// `next_ranks` is L1-renormalised (divided by the total mass unconditionally,
/// matching the C++ kernel which has no `total > 0` guard here). `delta` is the
/// L1 change `sum(|next - prev|)`.
// CSR `indptr`/`indices` entries are non-negative offsets by construction (a
// valid CSR matrix never stores a negative index), so the i32 -> usize index
// casts cannot lose a sign or truncate for any real graph. `node_count as f64`
// is exact for any graph whose node count fits in f64's 52-bit mantissa.
#[allow(
    clippy::cast_sign_loss,
    clippy::cast_possible_truncation,
    clippy::cast_precision_loss
)]
#[must_use]
pub fn pagerank_step_core(
    indptr: &[i32],
    indices: &[i32],
    data: &[f64],
    ranks: &[f64],
    dangling: &[bool],
    damping: f64,
    node_count: usize,
) -> (Vec<f64>, f64) {
    let mut next = vec![0.0_f64; node_count];
    let mut dangling_mass = 0.0_f64;
    for row in 0..node_count {
        let mut link_mass = 0.0_f64;
        for idx in indptr[row]..indptr[row + 1] {
            let col = indices[idx as usize] as usize;
            link_mass = data[idx as usize].mul_add(ranks[col], link_mass);
        }
        next[row] = (1.0 - damping) * link_mass;
        if dangling[row] {
            dangling_mass += ranks[row];
        }
    }

    let base_mass = (1.0 - damping).mul_add(dangling_mass, damping) / node_count as f64;
    let mut total_mass = 0.0_f64;
    for value in &mut next {
        *value += base_mass;
        total_mass += *value;
    }
    for value in &mut next {
        *value /= total_mass;
    }

    let mut delta = 0.0_f64;
    for (next_val, &prev) in next.iter().zip(ranks.iter()) {
        delta += (next_val - prev).abs();
    }
    (next, delta)
}

/// One personalized PageRank step. Returns `(next_ranks, delta)`.
///
/// Like [`pagerank_step_core`] but the teleport mass is distributed by the
/// `personalization` vector, and renormalisation divides by the total mass ONLY
/// when it is positive (matching the C++ `if (total_mass > 0.0)` guard).
// CSR indices are non-negative by construction; see `pagerank_step_core`. The
// 8-arg signature mirrors the C++ kernel's parameter contract exactly.
#[allow(
    clippy::cast_sign_loss,
    clippy::cast_possible_truncation,
    clippy::too_many_arguments
)]
#[must_use]
pub fn personalized_pagerank_step_core(
    indptr: &[i32],
    indices: &[i32],
    data: &[f64],
    ranks: &[f64],
    dangling: &[bool],
    personalization: &[f64],
    damping: f64,
    node_count: usize,
) -> (Vec<f64>, f64) {
    let mut next = vec![0.0_f64; node_count];
    let mut dangling_mass = 0.0_f64;
    for row in 0..node_count {
        let mut link_mass = 0.0_f64;
        for idx in indptr[row]..indptr[row + 1] {
            let col = indices[idx as usize] as usize;
            link_mass = data[idx as usize].mul_add(ranks[col], link_mass);
        }
        next[row] = (1.0 - damping) * link_mass;
        if dangling[row] {
            dangling_mass += ranks[row];
        }
    }

    let teleport_mass = (1.0 - damping).mul_add(dangling_mass, damping);
    let mut total_mass = 0.0_f64;
    for (value, &p) in next.iter_mut().zip(personalization.iter()) {
        *value += teleport_mass * p;
        total_mass += *value;
    }
    if total_mass > 0.0 {
        for value in &mut next {
            *value /= total_mass;
        }
    }

    let mut delta = 0.0_f64;
    for (next_val, &prev) in next.iter().zip(ranks.iter()) {
        delta += (next_val - prev).abs();
    }
    (next, delta)
}

/// One weighted Kleinberg HITS step. Returns `(next_authority, next_hub)`.
///
/// Both output buffers start at zero; for each CSR edge `u -> v` with weight
/// `w`: `next_authority[v] += w * hub[u]` and `next_hub[u] += w * authority[v]`.
/// No normalisation — the Python driver owns it.
// CSR indices are non-negative by construction; see `pagerank_step_core`.
#[allow(clippy::cast_sign_loss, clippy::cast_possible_truncation)]
#[must_use]
pub fn hits_step_core(
    indptr: &[i32],
    indices: &[i32],
    data: &[f64],
    authority: &[f64],
    hub: &[f64],
    node_count: usize,
) -> (Vec<f64>, Vec<f64>) {
    let mut next_authority = vec![0.0_f64; node_count];
    let mut next_hub = vec![0.0_f64; node_count];
    for v in 0..node_count {
        for idx in indptr[v]..indptr[v + 1] {
            let u = indices[idx as usize] as usize;
            let w = data[idx as usize];
            next_authority[v] = w.mul_add(hub[u], next_authority[v]);
            next_hub[u] = w.mul_add(authority[v], next_hub[u]);
        }
    }
    (next_authority, next_hub)
}

/// Validate `node_count >= 0` and `indptr` length, returning the count as usize.
/// `ndim_ok` was already enforced structurally by `PyReadonlyArray1`. The order
/// of these checks matches the C++ kernel so the first failing message wins.
fn check_common(node_count: i64, indptr_len: usize) -> PyResult<usize> {
    let n = usize::try_from(node_count)
        .map_err(|_| PyRuntimeError::new_err("node_count must be non-negative"))?;
    if indptr_len != n + 1 {
        return Err(PyRuntimeError::new_err(
            "indptr length must be node_count + 1",
        ));
    }
    Ok(n)
}

/// `pagerank_step(...) -> (np.ndarray[f64], float)`.
#[pyfunction]
#[allow(clippy::too_many_arguments, clippy::needless_pass_by_value)]
fn pagerank_step<'py>(
    py: Python<'py>,
    indptr: PyReadonlyArray1<'py, i32>,
    indices: PyReadonlyArray1<'py, i32>,
    data: PyReadonlyArray1<'py, f64>,
    ranks: PyReadonlyArray1<'py, f64>,
    dangling_mask: PyReadonlyArray1<'py, bool>,
    damping: f64,
    node_count: i64,
) -> PyResult<Bound<'py, PyTuple>> {
    let indptr_s = indptr.as_slice()?;
    let indices_s = indices.as_slice()?;
    let data_s = data.as_slice()?;
    let ranks_s = ranks.as_slice()?;
    let dangling_s = dangling_mask.as_slice()?;

    let n = check_common(node_count, indptr_s.len())?;
    if ranks_s.len() != n {
        return Err(PyRuntimeError::new_err(
            "ranks length must equal node_count",
        ));
    }
    if dangling_s.len() != n {
        return Err(PyRuntimeError::new_err(
            "dangling_mask length must equal node_count",
        ));
    }
    if indices_s.len() != data_s.len() {
        return Err(PyRuntimeError::new_err(
            "indices and data must have the same length",
        ));
    }

    let (next, delta) = py.detach(|| {
        pagerank_step_core(indptr_s, indices_s, data_s, ranks_s, dangling_s, damping, n)
    });
    let arr = next.into_pyarray(py);
    PyTuple::new(py, [arr.into_any(), delta.into_pyobject(py)?.into_any()])
}

/// `personalized_pagerank_step(...) -> (np.ndarray[f64], float)`.
#[pyfunction]
#[allow(clippy::too_many_arguments, clippy::needless_pass_by_value)]
fn personalized_pagerank_step<'py>(
    py: Python<'py>,
    indptr: PyReadonlyArray1<'py, i32>,
    indices: PyReadonlyArray1<'py, i32>,
    data: PyReadonlyArray1<'py, f64>,
    ranks: PyReadonlyArray1<'py, f64>,
    dangling_mask: PyReadonlyArray1<'py, bool>,
    personalization: PyReadonlyArray1<'py, f64>,
    damping: f64,
    node_count: i64,
) -> PyResult<Bound<'py, PyTuple>> {
    let indptr_s = indptr.as_slice()?;
    let indices_s = indices.as_slice()?;
    let data_s = data.as_slice()?;
    let ranks_s = ranks.as_slice()?;
    let dangling_s = dangling_mask.as_slice()?;
    let personalization_s = personalization.as_slice()?;

    let n = check_common(node_count, indptr_s.len())?;
    if ranks_s.len() != n {
        return Err(PyRuntimeError::new_err(
            "ranks length must equal node_count",
        ));
    }
    if dangling_s.len() != n {
        return Err(PyRuntimeError::new_err(
            "dangling_mask length must equal node_count",
        ));
    }
    if personalization_s.len() != n {
        return Err(PyRuntimeError::new_err(
            "personalization length must equal node_count",
        ));
    }
    if indices_s.len() != data_s.len() {
        return Err(PyRuntimeError::new_err(
            "indices and data must have the same length",
        ));
    }

    let (next, delta) = py.detach(|| {
        personalized_pagerank_step_core(
            indptr_s,
            indices_s,
            data_s,
            ranks_s,
            dangling_s,
            personalization_s,
            damping,
            n,
        )
    });
    let arr = next.into_pyarray(py);
    PyTuple::new(py, [arr.into_any(), delta.into_pyobject(py)?.into_any()])
}

/// `hits_step(...) -> (np.ndarray[f64], np.ndarray[f64])`.
#[pyfunction]
#[allow(clippy::needless_pass_by_value)]
fn hits_step<'py>(
    py: Python<'py>,
    indptr: PyReadonlyArray1<'py, i32>,
    indices: PyReadonlyArray1<'py, i32>,
    data: PyReadonlyArray1<'py, f64>,
    authority: PyReadonlyArray1<'py, f64>,
    hub: PyReadonlyArray1<'py, f64>,
    node_count: i64,
) -> PyResult<Bound<'py, PyTuple>> {
    let indptr_s = indptr.as_slice()?;
    let indices_s = indices.as_slice()?;
    let data_s = data.as_slice()?;
    let authority_s = authority.as_slice()?;
    let hub_s = hub.as_slice()?;

    let n = usize::try_from(node_count)
        .map_err(|_| PyRuntimeError::new_err("node_count must be non-negative"))?;
    if indptr_s.len() != n + 1 {
        return Err(PyRuntimeError::new_err(
            "indptr length must be node_count + 1",
        ));
    }
    if authority_s.len() != n {
        return Err(PyRuntimeError::new_err(
            "authority length must equal node_count",
        ));
    }
    if hub_s.len() != n {
        return Err(PyRuntimeError::new_err("hub length must equal node_count"));
    }
    if indices_s.len() != data_s.len() {
        return Err(PyRuntimeError::new_err(
            "indices and data must have the same length",
        ));
    }

    let (next_authority, next_hub) =
        py.detach(|| hits_step_core(indptr_s, indices_s, data_s, authority_s, hub_s, n));
    let auth_arr = next_authority.into_pyarray(py);
    let hub_arr = next_hub.into_pyarray(py);
    PyTuple::new(py, [auth_arr.into_any(), hub_arr.into_any()])
}

/// The Python module definition. The module name (`pagerank`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact imports as
/// `extensions.pagerank`. Registering all three functions keeps the health
/// probe's expected attribute (`pagerank_step`) present.
#[pymodule]
fn pagerank(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(pagerank_step, m)?)?;
    m.add_function(wrap_pyfunction!(personalized_pagerank_step, m)?)?;
    m.add_function(wrap_pyfunction!(hits_step, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{hits_step_core, pagerank_step_core, personalized_pagerank_step_core};

    // A tiny 3-node graph: edges 0->1, 1->2, 2->0 (a cycle), unit weights.
    // CSR is row=target: target 0 has source 2; target 1 has source 0; target 2
    // has source 1. So indptr=[0,1,2,3], indices=[2,0,1], data=[1,1,1].
    fn cycle_graph() -> (Vec<i32>, Vec<i32>, Vec<f64>) {
        (vec![0, 1, 2, 3], vec![2, 0, 1], vec![1.0, 1.0, 1.0])
    }

    #[test]
    fn pagerank_step_renormalises_to_one() {
        let (indptr, indices, data) = cycle_graph();
        let ranks = vec![1.0 / 3.0; 3];
        let dangling = vec![false; 3];
        let (next, _delta) =
            pagerank_step_core(&indptr, &indices, &data, &ranks, &dangling, 0.15, 3);
        let sum: f64 = next.iter().sum();
        assert!(
            (sum - 1.0).abs() < 1e-12,
            "ranks should sum to 1, got {sum}"
        );
    }

    #[test]
    fn pagerank_delta_is_non_negative() {
        let (indptr, indices, data) = cycle_graph();
        let ranks = vec![0.5, 0.3, 0.2];
        let dangling = vec![false; 3];
        let (_next, delta) =
            pagerank_step_core(&indptr, &indices, &data, &ranks, &dangling, 0.15, 3);
        assert!(delta >= 0.0, "delta must be non-negative, got {delta}");
    }

    #[test]
    fn pagerank_dangling_mass_redistributes() {
        // Node 2 is dangling: its rank mass feeds `dangling_mass`, which raises
        // `base_mass`. With NON-uniform ranks the per-row link-masses differ, so
        // adding more uniform `base_mass` (then renormalising) shifts the
        // distribution. A dangling vs non-dangling run must therefore differ.
        // Kills a mutant that ignores the `dangling_mask[row]` branch.
        let (indptr, indices, data) = cycle_graph();
        let ranks = vec![0.6, 0.3, 0.1];
        let with_dangling = vec![false, false, true];
        let no_dangling = vec![false; 3];
        let (a, _) = pagerank_step_core(&indptr, &indices, &data, &ranks, &with_dangling, 0.15, 3);
        let (b, _) = pagerank_step_core(&indptr, &indices, &data, &ranks, &no_dangling, 0.15, 3);
        assert!(
            (a[0] - b[0]).abs() > 1e-9 || (a[1] - b[1]).abs() > 1e-9 || (a[2] - b[2]).abs() > 1e-9,
            "dangling mask should change the result: {a:?} vs {b:?}"
        );
    }

    #[test]
    fn personalized_reduces_to_uniform_pagerank() {
        // With personalization[i] = 1/n the personalized step must match the
        // uniform pagerank step (within rounding).
        let (indptr, indices, data) = cycle_graph();
        let ranks = vec![0.5, 0.3, 0.2];
        let dangling = vec![false, false, true];
        let uniform = vec![1.0 / 3.0; 3];
        let (a, da) = pagerank_step_core(&indptr, &indices, &data, &ranks, &dangling, 0.15, 3);
        let (b, db) = personalized_pagerank_step_core(
            &indptr, &indices, &data, &ranks, &dangling, &uniform, 0.15, 3,
        );
        for i in 0..3 {
            assert!(
                (a[i] - b[i]).abs() < 1e-12,
                "mismatch at {i}: {} vs {}",
                a[i],
                b[i]
            );
        }
        assert!((da - db).abs() < 1e-12);
    }

    #[test]
    fn personalized_seeds_toward_target_node() {
        // All teleport mass on node 0 should push node 0's rank above the others.
        let (indptr, indices, data) = cycle_graph();
        let ranks = vec![1.0 / 3.0; 3];
        let dangling = vec![false; 3];
        let seed = vec![1.0, 0.0, 0.0];
        let (next, _d) = personalized_pagerank_step_core(
            &indptr, &indices, &data, &ranks, &dangling, &seed, 0.5, 3,
        );
        assert!(
            next[0] > next[1] && next[0] > next[2],
            "seed node should rank highest"
        );
    }

    #[test]
    fn hits_zeroes_then_deposits() {
        // edge 0->1 with weight 2: next_authority[1] += 2*hub[0];
        // next_hub[0] += 2*authority[1]. With hub=[1,1], authority=[1,1]:
        // next_authority[1]=2, next_hub[0]=2, everything else 0.
        let indptr = vec![0, 0, 1]; // target 0 has no source; target 1 has source 0
        let indices = vec![0];
        let data = vec![2.0];
        let authority = vec![1.0, 1.0];
        let hub = vec![1.0, 1.0];
        let (na, nh) = hits_step_core(&indptr, &indices, &data, &authority, &hub, 2);
        assert!(
            (na[0]).abs() < 1e-12 && (na[1] - 2.0).abs() < 1e-12,
            "authority {na:?}"
        );
        assert!(
            (nh[0] - 2.0).abs() < 1e-12 && (nh[1]).abs() < 1e-12,
            "hub {nh:?}"
        );
    }

    #[test]
    fn hits_weighted_recurrence_accumulates() {
        // Two edges into target 1: 0->1 (w=2) and... only one source per CSR
        // row here, so use a denser graph. target 1 has sources 0 and 2.
        let indptr = vec![0, 0, 2, 2];
        let indices = vec![0, 2];
        let data = vec![2.0, 3.0];
        let authority = vec![1.0, 1.0, 1.0];
        let hub = vec![1.0, 1.0, 1.0];
        let (na, nh) = hits_step_core(&indptr, &indices, &data, &authority, &hub, 3);
        // authority[1] = 2*hub[0] + 3*hub[2] = 2 + 3 = 5.
        assert!((na[1] - 5.0).abs() < 1e-12, "authority[1] {} != 5", na[1]);
        // hub[0] += 2*authority[1] = 2; hub[2] += 3*authority[1] = 3.
        assert!(
            (nh[0] - 2.0).abs() < 1e-12 && (nh[2] - 3.0).abs() < 1e-12,
            "hub {nh:?}"
        );
    }
}
