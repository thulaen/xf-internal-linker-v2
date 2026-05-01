#pragma once
#include <cstddef>
#include <cstdint>

extern "C" {
/**
 * Find the indices and distances of the top `nprobe` centroids closest to
 * a query vector (squared L2 distance).
 *
 * Inputs:
 *   query_ptr      — float[dim] query vector.
 *   centroids_ptr  — float[n_centroids * dim], row-major.
 *   n_centroids    — number of centroids in the array.
 *   dim            — vector dimension.
 *   nprobe         — how many centroids to return (1 ≤ nprobe ≤ n_centroids).
 *
 * Outputs (caller-provided buffers, length nprobe):
 *   out_centroid_ids   — int32[nprobe] partial-sorted centroid indices.
 *   out_centroid_dists — float[nprobe] matching squared L2 distances.
 *
 * Citation: Sivic-Zisserman 2003 ICCV (inverted file).
 */
void c_ivf_find_top_centroids(
    const float* query_ptr,
    const float* centroids_ptr,
    size_t n_centroids,
    size_t dim,
    size_t nprobe,
    int32_t* out_centroid_ids,
    float* out_centroid_dists);

/**
 * Build the per-query Asymmetric-Distance Computation (ADC) lookup table.
 *
 * For each subquantiser m and centroid k:
 *     LUT[m, k] = || rotated_query[m*sub_dim:(m+1)*sub_dim]
 *                  - codebook[m, k, :] ||²
 *
 * The query is first rotated by R: q' = q · R.
 *
 * Inputs:
 *   query_ptr      — float[dim].
 *   rotation_ptr   — float[dim * dim], row-major.
 *   codebooks_ptr  — float[m * k * sub_dim], row-major (M-K-D layout).
 *   dim, m, k      — geometry.
 *
 * Output:
 *   out_lut        — float[m * k] row-major.
 *
 * Citation: Jégou-Douze-Schmid 2010 CVPR (IVFADC).
 */
void c_ivf_build_adc_lut(
    const float* query_ptr,
    const float* rotation_ptr,
    const float* codebooks_ptr,
    size_t dim, size_t m, size_t k,
    float* out_lut);

/**
 * Compute the asymmetric L2² distance for one OPQ-coded vector against
 * a precomputed LUT.  Distance = Σ_m LUT[m, code[m]].
 *
 * Inputs:
 *   code_ptr — uint8[m] OPQ code.
 *   lut_ptr  — float[m * k] LUT from c_ivf_build_adc_lut().
 *   m, k     — geometry.
 *
 * Returns the scalar distance.
 */
float c_ivf_adc_distance(
    const uint8_t* code_ptr,
    const float* lut_ptr,
    size_t m, size_t k);
}
