#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>

#include <algorithm>
#include <cmath>
#include <vector>

#include "include/quantemb_core.h"

namespace py = pybind11;

/**
 * Perform OPQ encoding.
 * 1. Rotation: V' = V * R
 * 2. PQ: Find nearest centroid for each subvector
 */
void c_opq_encode(const float* vectors_ptr, size_t num_vectors, size_t dim,
                  const float* rotation_ptr, const float* codebooks_ptr, size_t m, size_t k,
                  uint8_t* out_codes) {
    size_t sub_dim = dim / m;

    for (size_t v_idx = 0; v_idx < num_vectors; ++v_idx) {
        const float* v_in = vectors_ptr + (v_idx * dim);
        std::vector<float> v_rot(dim, 0.0f);

        // 1. Apply Rotation
        for (size_t j = 0; j < dim; ++j) {
            float sum = 0.0f;
            for (size_t i = 0; i < dim; ++i) {
                sum += v_in[i] * rotation_ptr[i * dim + j];
            }
            v_rot[j] = sum;
        }

        // 2. PQ Encoding
        for (size_t m_idx = 0; m_idx < m; ++m_idx) {
            const float* sub_v = v_rot.data() + (m_idx * sub_dim);
            float min_dist = 1e30f;
            uint8_t best_k = 0;

            for (size_t k_idx = 0; k_idx < k; ++k_idx) {
                const float* centroid = codebooks_ptr + (m_idx * k * sub_dim) + (k_idx * sub_dim);
                float dist = 0.0f;
                for (size_t d = 0; d < sub_dim; ++d) {
                    float diff = sub_v[d] - centroid[d];
                    dist += diff * diff;
                }

                if (dist < min_dist) {
                    min_dist = dist;
                    best_k = (uint8_t)k_idx;
                }
            }
            out_codes[v_idx * m + m_idx] = best_k;
        }
    }
}

/**
 * Python wrapper for opq_encode.
 * Expects:
 *   vectors: np.array((N, dim), dtype=float32)
 *   rotation: np.array((dim, dim), dtype=float32)
 *   codebooks: np.array((m, k, sub_dim), dtype=float32)
 * Returns: np.array((N, m), dtype=uint8)
 */
py::array_t<uint8_t> opq_encode(py::array_t<float> vectors, py::array_t<float> rotation,
                                py::array_t<float> codebooks) {
    py::buffer_info v_info = vectors.request();
    py::buffer_info r_info = rotation.request();
    py::buffer_info cb_info = codebooks.request();

    if (v_info.ndim != 2)
        throw std::runtime_error("Vectors must be 2D");
    if (r_info.ndim != 2)
        throw std::runtime_error("Rotation must be 2D");
    if (cb_info.ndim != 3)
        throw std::runtime_error("Codebooks must be 3D");

    size_t num_vectors = (size_t)v_info.shape[0];
    size_t dim = (size_t)v_info.shape[1];
    size_t m = (size_t)cb_info.shape[0];
    size_t k = (size_t)cb_info.shape[1];
    size_t sub_dim = (size_t)cb_info.shape[2];

    if (dim != (size_t)r_info.shape[0] || dim != (size_t)r_info.shape[1])
        throw std::runtime_error("Rotation shape mismatch");
    if (dim != m * sub_dim)
        throw std::runtime_error("Codebook dimension mismatch");

    auto result = py::array_t<uint8_t>({(py::ssize_t)num_vectors, (py::ssize_t)m});
    py::buffer_info res_info = result.request();

    c_opq_encode(static_cast<const float*>(v_info.ptr), num_vectors, dim,
                 static_cast<const float*>(r_info.ptr), static_cast<const float*>(cb_info.ptr), m,
                 k, static_cast<uint8_t*>(res_info.ptr));

    return result;
}

PYBIND11_MODULE(quantemb, m) {
    m.doc() = "Vector quantization and OPQ kernels";
    m.def("opq_encode", &opq_encode, "Perform OPQ encoding on vectors");
}
