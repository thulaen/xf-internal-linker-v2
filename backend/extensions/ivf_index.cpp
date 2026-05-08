// Inverted File index search over OPQ-quantised vectors.
//
// Pattern: train k-means in Python (offline; not the hot path) and persist
// per-vector partition assignments. At query time we:
//   1. Find nprobe centroids closest to the query (cheap — N=4096, dim=1024).
//   2. Build a per-query ADC lookup table (m × k floats).
//   3. Walk every OPQ code in the chosen partitions, scoring via ADC.
//   4. Return the global indices of the top-k nearest.
//
// Why C++:
//   * Steps 1, 3, 4 each touch hundreds-of-thousands of vectors per query.
//   * The ADC inner loop is M=8 byte loads + M LUT reads — fits in L1 cache
//     and benefits massively from a tight C++ loop versus Python's overhead.
//   * Heap-based top-k avoids sorting the full result set.
//
// Citations:
//   * Sivic-Zisserman 2003 ICCV — inverted file for visual word retrieval.
//   * Jégou-Douze-Schmid 2010 CVPR — IVFADC asymmetric distance computation.
//   * Subramanya 2019 NeurIPS — DiskANN overflow path (future work for
//                                indexes that exceed the 512 MB working set).
//
// Parity floor (CPP-RULES §25): top-k indices must match a NumPy reference
// to ≤1e-4 absolute distance and ≥0.95 recall@100 vs FAISS (FR-053 §3 gate).

#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <queue>
#include <stdexcept>
#include <vector>

#ifndef XF_BENCH_MODE
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py = pybind11;
#endif

#include "include/ivf_index_core.h"

extern "C" {

void c_ivf_find_top_centroids(const float* query_ptr, const float* centroids_ptr,
                              size_t n_centroids, size_t dim, size_t nprobe,
                              int32_t* out_centroid_ids, float* out_centroid_dists) {
    // Compute L2² to every centroid. N=4096 × dim=1024 = ~4M flops per
    // query — milliseconds even on the i5-12450H.
    std::vector<std::pair<float, int32_t>> distances;
    distances.reserve(n_centroids);
    for (size_t c = 0; c < n_centroids; ++c) {
        const float* centroid = centroids_ptr + (c * dim);
        float dist = 0.0f;
        for (size_t d = 0; d < dim; ++d) {
            const float diff = query_ptr[d] - centroid[d];
            dist += diff * diff;
        }
        distances.emplace_back(dist, static_cast<int32_t>(c));
    }

    const size_t k = nprobe < n_centroids ? nprobe : n_centroids;
    std::partial_sort(distances.begin(), distances.begin() + static_cast<std::ptrdiff_t>(k),
                      distances.end(),
                      [](const std::pair<float, int32_t>& a, const std::pair<float, int32_t>& b) {
                          return a.first < b.first;
                      });

    for (size_t i = 0; i < k; ++i) {
        out_centroid_ids[i] = distances[i].second;
        out_centroid_dists[i] = distances[i].first;
    }
}

void c_ivf_build_adc_lut(const float* query_ptr, const float* rotation_ptr,
                         const float* codebooks_ptr, size_t dim, size_t m, size_t k,
                         float* out_lut) {
    if (m == 0 || dim % m != 0) {
        // Degenerate input: zero-fill so the caller gets a deterministic
        // "no preference" LUT instead of garbage memory.
        for (size_t i = 0; i < m * k; ++i)
            out_lut[i] = 0.0f;
        return;
    }
    const size_t sub_dim = dim / m;

    // 1. Rotate the query: q_rot = q · R.
    std::vector<float> q_rot(dim, 0.0f);
    for (size_t j = 0; j < dim; ++j) {
        float sum = 0.0f;
        for (size_t i = 0; i < dim; ++i) {
            sum += query_ptr[i] * rotation_ptr[i * dim + j];
        }
        q_rot[j] = sum;
    }

    // 2. For each (m, k) compute squared L2 between q_rot's m-th
    //    subvector and codebook[m, k, :].
    for (size_t m_idx = 0; m_idx < m; ++m_idx) {
        const float* sub_q = q_rot.data() + (m_idx * sub_dim);
        for (size_t k_idx = 0; k_idx < k; ++k_idx) {
            const float* centroid = codebooks_ptr + (m_idx * k * sub_dim) + (k_idx * sub_dim);
            float dist = 0.0f;
            for (size_t d = 0; d < sub_dim; ++d) {
                const float diff = sub_q[d] - centroid[d];
                dist += diff * diff;
            }
            out_lut[m_idx * k + k_idx] = dist;
        }
    }
}

float c_ivf_adc_distance(const uint8_t* code_ptr, const float* lut_ptr, size_t m, size_t k) {
    float total = 0.0f;
    for (size_t m_idx = 0; m_idx < m; ++m_idx) {
        total += lut_ptr[m_idx * k + static_cast<size_t>(code_ptr[m_idx])];
    }
    return total;
}

}  // extern "C"

#ifndef XF_BENCH_MODE

// ---------------------------------------------------------------------------
// pybind11 wrappers
// ---------------------------------------------------------------------------

/**
 * Top-level retrieval-time function: IVF + OPQ asymmetric-distance search.
 *
 * Args:
 *   query                   — float32[dim] query vector.
 *   centroids               — float32[n_centroids, dim] IVF centroids.
 *   partition_member_lists  — list of N_centroids inner lists; inner list i
 *                             contains the global indices of vectors assigned
 *                             to centroid i.
 *   opq_codes               — uint8[N_total, m] OPQ codes (one row per global
 *                             vector index).
 *   rotation                — float32[dim, dim] OPQ rotation matrix R.
 *   codebooks               — float32[m, k, sub_dim] OPQ sub-codebooks.
 *   nprobe                  — how many centroids to inspect (default 16).
 *   top_k                   — how many results to return (default 100).
 *
 * Returns:
 *   int32[top_k] — global indices of the nearest neighbours, ordered by
 *                  ascending ADC distance.
 */
static py::array_t<int32_t> ivf_search(
    py::array_t<float, py::array::c_style | py::array::forcecast> query,
    py::array_t<float, py::array::c_style | py::array::forcecast> centroids,
    // pybind11-bound entry point; the by-value vector signature is the
    // contract Python sees. Switching to const& would change the binding.
    std::vector<std::vector<int32_t>> partition_member_lists,
    py::array_t<uint8_t, py::array::c_style | py::array::forcecast> opq_codes,
    py::array_t<float, py::array::c_style | py::array::forcecast> rotation,
    py::array_t<float, py::array::c_style | py::array::forcecast> codebooks, int nprobe,
    int top_k) {
    const auto q_info = query.request();
    const auto c_info = centroids.request();
    const auto codes_info = opq_codes.request();
    const auto r_info = rotation.request();
    const auto cb_info = codebooks.request();

    if (q_info.ndim != 1)
        throw std::runtime_error("query must be 1D");
    if (c_info.ndim != 2)
        throw std::runtime_error("centroids must be 2D");
    if (codes_info.ndim != 2)
        throw std::runtime_error("opq_codes must be 2D");
    if (r_info.ndim != 2)
        throw std::runtime_error("rotation must be 2D");
    if (cb_info.ndim != 3)
        throw std::runtime_error("codebooks must be 3D (m, k, sub_dim)");

    const size_t dim = static_cast<size_t>(q_info.shape[0]);
    const size_t n_centroids = static_cast<size_t>(c_info.shape[0]);
    const size_t n_total = static_cast<size_t>(codes_info.shape[0]);
    const size_t m = static_cast<size_t>(codes_info.shape[1]);
    const size_t k = static_cast<size_t>(cb_info.shape[1]);

    if (static_cast<size_t>(c_info.shape[1]) != dim)
        throw std::runtime_error("centroids second dim must equal query dim");
    if (static_cast<size_t>(cb_info.shape[0]) != m)
        throw std::runtime_error("codebooks first dim (m) must equal opq_codes second dim");
    if (static_cast<size_t>(r_info.shape[0]) != dim || static_cast<size_t>(r_info.shape[1]) != dim)
        throw std::runtime_error("rotation must be (dim, dim)");
    if (partition_member_lists.size() != n_centroids)
        throw std::runtime_error("partition_member_lists length must equal n_centroids");
    if (nprobe < 1 || static_cast<size_t>(nprobe) > n_centroids)
        throw std::runtime_error("nprobe must be in [1, n_centroids]");
    if (top_k < 1)
        throw std::runtime_error("top_k must be >= 1");

    const float* query_ptr = static_cast<const float*>(q_info.ptr);
    const float* centroids_ptr = static_cast<const float*>(c_info.ptr);
    const uint8_t* codes_ptr = static_cast<const uint8_t*>(codes_info.ptr);
    const float* rotation_ptr = static_cast<const float*>(r_info.ptr);
    const float* codebooks_ptr = static_cast<const float*>(cb_info.ptr);

    // 1. Top-nprobe centroids.
    std::vector<int32_t> centroid_ids(static_cast<size_t>(nprobe));
    std::vector<float> centroid_dists(static_cast<size_t>(nprobe));
    c_ivf_find_top_centroids(query_ptr, centroids_ptr, n_centroids, dim,
                             static_cast<size_t>(nprobe), centroid_ids.data(),
                             centroid_dists.data());

    // 2. Per-query ADC LUT.
    std::vector<float> lut(m * k);
    c_ivf_build_adc_lut(query_ptr, rotation_ptr, codebooks_ptr, dim, m, k, lut.data());

    // 3. Bounded top-k via max-heap (so the worst kept item sits at the
    //    top and we can pop+push in O(log top_k)).
    using ScoredItem = std::pair<float, int32_t>;
    auto cmp = [](const ScoredItem& a, const ScoredItem& b) { return a.first < b.first; };
    std::priority_queue<ScoredItem, std::vector<ScoredItem>, decltype(cmp)> heap(cmp);
    const size_t target = static_cast<size_t>(top_k);

    for (int32_t centroid_id : centroid_ids) {
        if (centroid_id < 0 || static_cast<size_t>(centroid_id) >= n_centroids)
            continue;
        const auto& members = partition_member_lists[static_cast<size_t>(centroid_id)];
        for (int32_t vec_idx : members) {
            if (vec_idx < 0 || static_cast<size_t>(vec_idx) >= n_total)
                continue;
            const uint8_t* code = codes_ptr + (static_cast<size_t>(vec_idx) * m);
            const float dist = c_ivf_adc_distance(code, lut.data(), m, k);

            if (heap.size() < target) {
                heap.emplace(dist, vec_idx);
            } else if (dist < heap.top().first) {
                heap.pop();
                heap.emplace(dist, vec_idx);
            }
        }
    }

    // 4. Drain heap and sort ascending by distance.
    std::vector<ScoredItem> results;
    results.reserve(heap.size());
    while (!heap.empty()) {
        results.push_back(heap.top());
        heap.pop();
    }
    std::sort(results.begin(), results.end(),
              [](const ScoredItem& a, const ScoredItem& b) { return a.first < b.first; });

    auto out = py::array_t<int32_t>(static_cast<py::ssize_t>(results.size()));
    auto out_buf = out.request();
    int32_t* out_ptr = static_cast<int32_t*>(out_buf.ptr);
    for (size_t i = 0; i < results.size(); ++i) {
        out_ptr[i] = results[i].second;
    }
    return out;
}

/**
 * Per-destination ADC scoring used by FR-053 ``passage_relevance.score()``.
 *
 * Loads only the OPQ codes for ONE destination (typically <50 passages),
 * builds the per-query ADC LUT once, scores each code, returns the
 * best (index, similarity) pair where similarity = 1 - sqrt(dist)/2
 * mapped from squared-L2 back to cosine. Both the query and the codes
 * encode L2-normalised vectors so the back-projection is exact.
 *
 * Args:
 *   query                  — float32[dim].
 *   opq_codes              — uint8[N_passages, m] for this destination.
 *   rotation, codebooks    — current OPQ codebook.
 *
 * Returns: tuple (best_index, best_cosine_sim).
 *
 * Why a separate function from ``ivf_search``: ``ivf_search`` walks IVF
 * partitions across the WHOLE corpus to find top-k destinations.
 * ``adc_score_destination`` scores one already-chosen destination's
 * passages — the per-destination scoring step in the ranker hot path.
 */
static py::tuple adc_score_destination(
    py::array_t<float, py::array::c_style | py::array::forcecast> query,
    py::array_t<uint8_t, py::array::c_style | py::array::forcecast> opq_codes,
    py::array_t<float, py::array::c_style | py::array::forcecast> rotation,
    py::array_t<float, py::array::c_style | py::array::forcecast> codebooks) {
    const auto q_info = query.request();
    const auto codes_info = opq_codes.request();
    const auto r_info = rotation.request();
    const auto cb_info = codebooks.request();

    if (q_info.ndim != 1)
        throw std::runtime_error("query must be 1D");
    if (codes_info.ndim != 2)
        throw std::runtime_error("opq_codes must be 2D");
    if (r_info.ndim != 2)
        throw std::runtime_error("rotation must be 2D");
    if (cb_info.ndim != 3)
        throw std::runtime_error("codebooks must be 3D (m, k, sub_dim)");

    const size_t dim = static_cast<size_t>(q_info.shape[0]);
    const size_t n_passages = static_cast<size_t>(codes_info.shape[0]);
    const size_t m = static_cast<size_t>(codes_info.shape[1]);
    const size_t k = static_cast<size_t>(cb_info.shape[1]);

    if (n_passages == 0) {
        return py::make_tuple(0, 0.0f);
    }
    if (static_cast<size_t>(cb_info.shape[0]) != m)
        throw std::runtime_error("codebooks first dim (m) must equal opq_codes second dim");
    if (static_cast<size_t>(r_info.shape[0]) != dim || static_cast<size_t>(r_info.shape[1]) != dim)
        throw std::runtime_error("rotation must be (dim, dim)");

    const float* query_ptr = static_cast<const float*>(q_info.ptr);
    const uint8_t* codes_ptr = static_cast<const uint8_t*>(codes_info.ptr);
    const float* rotation_ptr = static_cast<const float*>(r_info.ptr);
    const float* codebooks_ptr = static_cast<const float*>(cb_info.ptr);

    std::vector<float> lut(m * k);
    c_ivf_build_adc_lut(query_ptr, rotation_ptr, codebooks_ptr, dim, m, k, lut.data());

    int best_idx = 0;
    float best_dist = 1e30f;
    for (size_t i = 0; i < n_passages; ++i) {
        const uint8_t* code = codes_ptr + (i * m);
        const float dist = c_ivf_adc_distance(code, lut.data(), m, k);
        if (dist < best_dist) {
            best_dist = dist;
            best_idx = static_cast<int>(i);
        }
    }

    // Squared-L2 between two L2-normalised vectors a and b is
    //   ||a-b||² = 2 - 2·cos(a, b)
    // so cos(a, b) = 1 - dist/2. Clamp to [0, 1] for numerical safety
    // (small negative cosines from quantisation noise become 0).
    const float cosine_sim = std::max(0.0f, std::min(1.0f, 1.0f - best_dist * 0.5f));
    return py::make_tuple(best_idx, cosine_sim);
}

PYBIND11_MODULE(ivf_index, m) {
    m.doc() =
        "Inverted File index search over OPQ-quantised vectors. "
        "Citations: Sivic-Zisserman 2003 ICCV (inverted file); "
        "Jegou-Douze-Schmid 2010 CVPR (IVFADC asymmetric distance).";
    m.def("ivf_search", &ivf_search,
          "IVF + OPQ asymmetric-distance search. Returns top-k global indices.", py::arg("query"),
          py::arg("centroids"), py::arg("partition_member_lists"), py::arg("opq_codes"),
          py::arg("rotation"), py::arg("codebooks"), py::arg("nprobe") = 16,
          py::arg("top_k") = 100);
    m.def("adc_score_destination", &adc_score_destination,
          "Per-destination OPQ ADC scoring. Returns (best_passage_index, "
          "best_cosine_similarity). Used by FR-053 passage_relevance.score().",
          py::arg("query"), py::arg("opq_codes"), py::arg("rotation"), py::arg("codebooks"));
}

#endif  // XF_BENCH_MODE
