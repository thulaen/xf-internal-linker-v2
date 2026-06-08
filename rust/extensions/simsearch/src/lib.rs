//! Bounded top-k dot-product sentence-search kernel, ported from the C++
//! `simsearch` kernel (`backend/extensions/simsearch.cpp`) to Rust and exposed
//! to Python as the native module `extensions.simsearch` via `PyO3` + the
//! `numpy` crate.
//!
//! The runtime calls `from extensions import simsearch` and then
//! `simsearch.score_and_topk(destination, sentences, candidate_rows, top_k)`
//! from `apps/pipeline/services/pipeline_stages.py::_score_sentences_stage2`
//! (Stage-2 sentence scoring). The Python-callable API matches the C++ kernel
//! exactly:
//!
//! - [`score_and_topk`] — given a 1-D float32 destination (query) embedding, a
//!   2-D C-contiguous float32 sentence matrix, a 1-D int32 array of candidate
//!   row indices, and an integer `top_k`, returns a 2-tuple
//!   `(indices, scores)` where `indices` is an int64 array of the **positions
//!   in the `candidate_rows` list** (NOT the underlying sentence row indices)
//!   whose dot product with the destination is largest, and `scores` is the
//!   matching float32 dot products. Both arrays have the same length
//!   `min(top_k, valid_candidate_count)` and are sorted by score descending.
//!
//! The compute core ([`score_and_topk_core`]) is plain Rust over `&[f32]` /
//! `&[i32]` slices so it is unit-testable with `cargo test` without crossing
//! the Python boundary.
//!
//! ## Port contract notes (parity basis: `contract`, not byte-exact)
//!
//! - **Emit candidate-LIST position, never the row index.** The C++ pushes
//!   `(int64_t)i` (the loop index over `candidate_rows`), and the production
//!   caller maps it back to a sentence id via `candidate_ids[i]`. This port
//!   preserves that exactly.
//! - **Dot product** is a serial single-precision (`f32`) running sum over the
//!   first `min(dest_dim, sentence_dim)` elements, using `mul_add` (one
//!   rounding step, maps to a hardware FMA). It is a raw dot product — NO
//!   normalization in the kernel (embeddings are pre-normalized upstream).
//! - **Out-of-range candidate rows** (`row_idx < 0` or
//!   `row_idx >= num_sentences`) are skipped, so they never appear in the
//!   result and reduce the output length below `top_k`.
//! - **Ordering** is score DESCENDING. To make the result deterministic the
//!   port breaks ties by candidate-list position ASCENDING (the C++ min-heap
//!   left ties implementation-defined; for distinct scores both give the same
//!   set and order). This is allowed because the parity basis is `contract`
//!   and no caller depends on the C++ tie order.
//! - **`top_k == 0`** yields an empty result; **`candidate_count == 0`** yields
//!   two length-0 arrays.
//!
//! Source of truth: cosine top-k retrieval over `BGE-M3` embeddings (Chen et al.
//! 2024, `BGE-M3`; cosine similarity from the vector space model, Salton 1975 /
//! Salton and `McGill`, Introduction to Modern Information Retrieval, 1983), as
//! registered in `signal_registry.py` (`semantic_similarity`,
//! `cpp_kernel=simsearch.score_and_topk`) and `meta_registry.py` (META-07).

use numpy::{IntoPyArray, PyArray1, PyReadonlyArray1, PyReadonlyArray2, PyUntypedArrayMethods};
use pyo3::prelude::*;

/// The result of [`score_and_topk_core`]: the selected candidate-list positions
/// and their matching dot-product scores, index-aligned and equal length.
type TopK = (Vec<i64>, Vec<f32>);

/// The Python-facing return of [`score_and_topk`]: an int64 index array and a
/// float32 score array, returned to Python as a 2-tuple.
type PyTopK<'py> = (Bound<'py, PyArray1<i64>>, Bound<'py, PyArray1<f32>>);

/// Compute the bounded top-k of candidate sentences by dot-product score.
///
/// # Arguments
/// * `destination` — the query embedding, length `dest_dim`.
/// * `sentences` — row-major sentence matrix, length `num_sentences *
///   sentence_dim`.
/// * `sentence_dim` — the row stride of `sentences`.
/// * `num_sentences` — the number of rows in `sentences`.
/// * `candidate_rows` — row indices into `sentences` to score.
/// * `top_k` — the maximum number of results to return.
///
/// # Returns
/// `(indices, scores)` where `indices[j]` is the **position in
/// `candidate_rows`** (not the sentence row index) of the `j`-th best
/// candidate, and `scores[j]` is its dot product with `destination`. The
/// vectors have equal length `min(top_k, valid_candidate_count)` and are sorted
/// by score descending, ties broken by candidate-list position ascending.
///
/// Candidate rows outside `[0, num_sentences)` are skipped. The dot product
/// runs over `min(dest_dim, sentence_dim)` elements, tolerating a dimension
/// mismatch by truncating to the shorter.
#[must_use]
pub fn score_and_topk_core(
    destination: &[f32],
    sentences: &[f32],
    sentence_dim: usize,
    num_sentences: usize,
    candidate_rows: &[i32],
    top_k: usize,
) -> TopK {
    if top_k == 0 || candidate_rows.is_empty() {
        return (Vec::new(), Vec::new());
    }

    let dest_dim = destination.len();
    let dot_dim = dest_dim.min(sentence_dim);

    // Collect (candidate-list position, score) for every in-range candidate.
    let mut scored: Vec<(i64, f32)> = Vec::with_capacity(candidate_rows.len());
    for (i, &row_idx) in candidate_rows.iter().enumerate() {
        // Skip rows outside [0, num_sentences). `try_from` rejects the negative
        // case losslessly, so a `row_idx < 0` candidate is skipped exactly like
        // the C++ kernel's `row_idx < 0` guard.
        let Ok(row) = usize::try_from(row_idx) else {
            continue;
        };
        if row >= num_sentences {
            continue;
        }
        let base = row * sentence_dim;
        let sentence = &sentences[base..base + sentence_dim];
        let mut dot: f32 = 0.0;
        for d in 0..dot_dim {
            // Fused multiply-add: one rounding step, maps to a hardware FMA;
            // clippy's `suboptimal_flops` flags the separate `+= a * b` form.
            dot = destination[d].mul_add(sentence[d], dot);
        }
        // `i` is the candidate-list position, NOT `row_idx`. The production
        // caller maps it back to a sentence id via `candidate_ids[i]`. `i` is a
        // slice index, so on any real input it is far below `i64::MAX`; the
        // `unwrap_or` keeps the function panic-free for the unreachable
        // overflow case instead of using an unchecked cast.
        let position = i64::try_from(i).unwrap_or(i64::MAX);
        scored.push((position, dot));
    }

    // Sort by score DESCENDING, ties broken by candidate-list position
    // ASCENDING for deterministic, reproducible output.
    scored.sort_by(|a, b| {
        b.1.partial_cmp(&a.1)
            .unwrap_or(std::cmp::Ordering::Equal)
            .then(a.0.cmp(&b.0))
    });

    let out_count = top_k.min(scored.len());
    let mut indices = Vec::with_capacity(out_count);
    let mut out_scores = Vec::with_capacity(out_count);
    for &(idx, score) in scored.iter().take(out_count) {
        indices.push(idx);
        out_scores.push(score);
    }
    (indices, out_scores)
}

/// Score candidates and return the top-k candidate-list positions and scores.
///
/// Mirrors the C++ `score_and_topk`. The `numpy` crate gives zero-copy
/// read-only views over the float32 destination/sentence arrays and the int32
/// candidate-row array; the int64 index and float32 score outputs are built as
/// fresh numpy arrays. See the module docstring for the full port contract.
#[pyfunction]
#[allow(clippy::needless_pass_by_value)]
fn score_and_topk<'py>(
    py: Python<'py>,
    destination: PyReadonlyArray1<'py, f32>,
    sentences: PyReadonlyArray2<'py, f32>,
    candidate_rows: PyReadonlyArray1<'py, i32>,
    top_k: i64,
) -> PyResult<PyTopK<'py>> {
    let sentence_shape = sentences.shape();
    let num_sentences = sentence_shape[0];
    let sentence_dim = sentence_shape[1];

    let destination_slice = destination.as_slice()?;
    let sentences_slice = sentences.as_slice()?;
    let candidate_slice = candidate_rows.as_slice()?;

    // A negative top_k means "no results" (the C++ allocated a zero-length
    // buffer and the heap never grew). `try_from` maps any negative value to
    // the empty-result path without an unchecked cast.
    let top_k_usize = usize::try_from(top_k).unwrap_or(0);

    let (indices, scores) = py.detach(|| {
        score_and_topk_core(
            destination_slice,
            sentences_slice,
            sentence_dim,
            num_sentences,
            candidate_slice,
            top_k_usize,
        )
    });

    Ok((indices.into_pyarray(py), scores.into_pyarray(py)))
}

/// The Python module definition. The module name (`simsearch`) MUST match the
/// `[lib] name` in `Cargo.toml` so the built artifact (`simsearch.so`) imports
/// as `extensions.simsearch` once it is staged on `PYTHONPATH` under
/// `extensions/`. The function name MUST be literally `score_and_topk` so the
/// critical native-runtime health probe
/// (`health.py::_NATIVE_RUNTIME_MODULES`) passes.
#[pymodule]
fn simsearch(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(score_and_topk, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    // The test fixtures build deterministic small integer values via `as f32`
    // / `as i32` / `as i64` casts that stay in a tiny bounded range, so the
    // precision/truncation/wrap lints do not apply; exact float compares on
    // those exact integer-valued scores are intentional.
    #![allow(
        clippy::float_cmp,
        clippy::cast_precision_loss,
        clippy::cast_possible_truncation,
        clippy::cast_possible_wrap
    )]

    use super::score_and_topk_core;

    /// Reference NumPy-style dot product computed in `f64` for an independent
    /// check of which candidate wins (kept separate from the `f32` kernel so a
    /// regression in the kernel cannot mask itself).
    fn ref_dot(dest: &[f32], row: &[f32]) -> f64 {
        let n = dest.len().min(row.len());
        (0..n).map(|d| f64::from(dest[d]) * f64::from(row[d])).sum()
    }

    #[test]
    fn empty_candidates_returns_two_empty_arrays() {
        let dest = [1.0_f32, 0.0];
        let sentences = [1.0_f32, 0.0, 0.0, 1.0];
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 2, 2, &[], 5);
        assert!(idx.is_empty());
        assert!(scores.is_empty());
    }

    #[test]
    fn top_k_zero_returns_empty() {
        let dest = [1.0_f32, 0.0];
        let sentences = [1.0_f32, 0.0, 0.0, 1.0];
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 2, 2, &[0, 1], 0);
        assert!(idx.is_empty());
        assert!(scores.is_empty());
    }

    #[test]
    fn returns_candidate_list_positions_not_row_indices() {
        // sentences row 0 = [1,0], row 1 = [0,1], row 2 = [1,1].
        let dest = [0.0_f32, 1.0];
        let sentences = [1.0_f32, 0.0, 0.0, 1.0, 1.0, 1.0];
        // candidate_rows = [2, 0, 1]: positions 0->row2 (dot 1), 1->row0 (dot 0),
        // 2->row1 (dot 1). Best two by score: row2 (pos 0) and row1 (pos 2),
        // both dot 1; tie broken by position ascending => [0, 2].
        let candidate_rows = [2_i32, 0, 1];
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 2, 3, &candidate_rows, 2);
        assert_eq!(idx, vec![0, 2], "must emit candidate-list positions");
        assert_eq!(scores, vec![1.0, 1.0]);
    }

    #[test]
    fn descending_score_order() {
        // dest = [1,0]; rows: 0=[0.2,0], 1=[0.9,0], 2=[0.5,0].
        let dest = [1.0_f32, 0.0];
        let sentences = [0.2_f32, 0.0, 0.9, 0.0, 0.5, 0.0];
        let candidate_rows = [0_i32, 1, 2];
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 2, 3, &candidate_rows, 3);
        // Best to worst: row1 (0.9, pos1), row2 (0.5, pos2), row0 (0.2, pos0).
        assert_eq!(idx, vec![1, 2, 0]);
        assert!(scores[0] > scores[1] && scores[1] > scores[2]);
    }

    #[test]
    fn skips_out_of_range_rows() {
        let dest = [1.0_f32, 0.0];
        // 2 rows; candidate_rows below includes -1 and 5 (both out of [0,2)).
        let sentences = [1.0_f32, 0.0, 0.5, 0.0];
        let candidate_rows = [-1_i32, 0, 5, 1];
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 2, 2, &candidate_rows, 10);
        // Only positions 1 (row0, dot1) and 3 (row1, dot0.5) survive.
        assert_eq!(idx, vec![1, 3]);
        assert_eq!(scores, vec![1.0, 0.5]);
        assert_eq!(idx.len(), 2, "out_count reduced below top_k by skips");
    }

    #[test]
    fn top_k_larger_than_valid_count_returns_all_valid() {
        let dest = [1.0_f32];
        let sentences = [2.0_f32, 3.0]; // 2 rows, dim 1
        let candidate_rows = [0_i32, 1];
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 1, 2, &candidate_rows, 100);
        assert_eq!(idx.len(), 2);
        assert_eq!(scores, vec![3.0, 2.0]); // row1 (3) before row0 (2)
        assert_eq!(idx, vec![1, 0]);
    }

    #[test]
    fn dim_mismatch_truncates_to_shorter() {
        // dest dim 3, sentence dim 2 -> dot uses first 2 elements only.
        let dest = [1.0_f32, 1.0, 100.0];
        let sentences = [2.0_f32, 3.0]; // 1 row, dim 2
        let candidate_rows = [0_i32];
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 2, 1, &candidate_rows, 1);
        assert_eq!(idx, vec![0]);
        // 1*2 + 1*3 = 5; the 100.0 in dest[2] is ignored.
        assert_eq!(scores, vec![5.0]);
    }

    #[test]
    fn tie_break_is_position_ascending() {
        // Two rows with identical score; lower candidate-list position wins
        // the earlier slot.
        let dest = [1.0_f32, 0.0];
        let sentences = [1.0_f32, 0.0, 1.0, 0.0]; // both rows = [1,0], dot 1
        let candidate_rows = [1_i32, 0]; // pos0->row1, pos1->row0
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 2, 2, &candidate_rows, 2);
        assert_eq!(idx, vec![0, 1], "ties resolve by position ascending");
        assert_eq!(scores, vec![1.0, 1.0]);
    }

    #[test]
    fn nan_score_does_not_panic_and_sorts_last() {
        // A NaN in the destination produces NaN dot products. partial_cmp
        // returns None for NaN; the unwrap_or(Equal) keeps the sort total and
        // panic-free. We only assert no panic and a length-2 result here.
        let dest = [f32::NAN, 1.0];
        let sentences = [0.0_f32, 1.0, 0.0, 0.5];
        let candidate_rows = [0_i32, 1];
        let (idx, scores) = score_and_topk_core(&dest, &sentences, 2, 2, &candidate_rows, 2);
        assert_eq!(idx.len(), 2);
        assert_eq!(scores.len(), 2);
    }

    #[test]
    fn many_vectors_parity_with_reference() {
        // 50 rows, dim 8, deterministic values; check the kernel's top-5 set
        // and descending order agree with an independent f64 reference over
        // the same candidate list.
        let num_sentences = 50_usize;
        let dim = 8_usize;
        let dest: Vec<f32> = (0..dim).map(|d| ((d * 7 % 11) as f32) - 5.0).collect();
        let mut sentences = Vec::with_capacity(num_sentences * dim);
        for r in 0..num_sentences {
            for d in 0..dim {
                sentences.push((((r * 13 + d * 5) % 97) as f32) - 48.0);
            }
        }
        let candidate_rows: Vec<i32> = (0..num_sentences as i32).collect();
        let top_k = 5;
        let (idx, scores) = score_and_topk_core(
            &dest,
            &sentences,
            dim,
            num_sentences,
            &candidate_rows,
            top_k,
        );
        assert_eq!(idx.len(), top_k);

        // Independent reference: compute every dot in f64, sort, take top-5.
        let mut ref_scored: Vec<(i64, f64)> = (0..num_sentences)
            .map(|r| {
                let row = &sentences[r * dim..r * dim + dim];
                (r as i64, ref_dot(&dest, row))
            })
            .collect();
        ref_scored.sort_by(|a, b| {
            b.1.partial_cmp(&a.1)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then(a.0.cmp(&b.0))
        });
        let ref_top: Vec<i64> = ref_scored.iter().take(top_k).map(|p| p.0).collect();
        // candidate_rows == [0,1,2,...] so position == row index here; the
        // returned positions must match the reference row order.
        assert_eq!(idx, ref_top, "top-5 set/order must match f64 reference");
        // Scores must be descending.
        for w in scores.windows(2) {
            assert!(w[0] >= w[1], "scores not descending: {scores:?}");
        }
    }
}
