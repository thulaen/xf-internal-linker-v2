#ifndef XF_BENCH_MODE
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
#endif

#include <algorithm>
#include <cmath>
#include <vector>

#include "include/passagesim_core.h"

#ifndef XF_BENCH_MODE
namespace py = pybind11;
#endif

/**
 * Core implementation of MaxSim using standard loops.
 * Optimized for cache locality by processing in blocks if needed,
 * but for V1 we keep it simple.
 */
void c_passagesim_maxsim(const float* query_ptr, const float* matrix_ptr, size_t num_passages,
                         size_t dim, float* out_sim, size_t* out_index) {
    if (num_passages == 0) {
        *out_sim = 0.0f;
        *out_index = 0;
        return;
    }

    float max_sim = -1e9f;
    size_t best_idx = 0;

    for (size_t i = 0; i < num_passages; ++i) {
        float dot = 0.0f;
        const float* row = matrix_ptr + (i * dim);
        for (size_t d = 0; d < dim; ++d) {
            dot += query_ptr[d] * row[d];
        }

        if (dot > max_sim) {
            max_sim = dot;
            best_idx = i;
        }
    }

    *out_sim = max_sim;
    *out_index = best_idx;
}

/**
 * Python wrapper for maxsim.
 * Expects:
 *   query: np.array(dim, dtype=float32)
 *   matrix: np.array((N, dim), dtype=float32)
 * Returns: (best_sim, best_idx)
 */
#ifndef XF_BENCH_MODE
py::tuple maxsim(py::array_t<float> query, py::array_t<float> matrix) {
    py::buffer_info q_info = query.request();
    py::buffer_info m_info = matrix.request();

    if (q_info.ndim != 1)
        throw std::runtime_error("Query must be 1D");
    if (m_info.ndim != 2)
        throw std::runtime_error("Matrix must be 2D");
    if (q_info.shape[0] != m_info.shape[1])
        throw std::runtime_error("Dimensions must match");

    size_t num_passages = (size_t)m_info.shape[0];
    size_t dim = (size_t)q_info.shape[0];

    float best_sim = 0.0f;
    size_t best_idx = 0;

    c_passagesim_maxsim(static_cast<const float*>(q_info.ptr),
                        static_cast<const float*>(m_info.ptr), num_passages, dim, &best_sim,
                        &best_idx);

    return py::make_tuple(best_sim, best_idx);
}

PYBIND11_MODULE(passagesim, m) {
    m.doc() = "Passage relevance similarity kernels";
    m.def("maxsim", &maxsim, "Compute maximum similarity across passages");
}
#endif
