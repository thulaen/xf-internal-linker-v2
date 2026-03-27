#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <cmath>
#include <vector>

namespace py = pybind11;

/**
 * L2 normalization for a 1D numpy array.
 * Uses AVX2 if available (auto-vectorized by compiler -O3).
 */
void normalize_l2(py::array_t<float> input) {
    auto buf = input.request();
    float* ptr = static_cast<float*>(buf.ptr);
    size_t size = buf.size;

    float sum_sq = 0.0f;
    for (size_t i = 0; i < size; ++i) {
        sum_sq += ptr[i] * ptr[i];
    }

    float norm = std::sqrt(sum_sq);
    if (norm > 1e-10f) {
        float inv_norm = 1.0f / norm;
        for (size_t i = 0; i < size; ++i) {
            ptr[i] *= inv_norm;
        }
    }
}

/**
 * L2 normalization for a 2D numpy array (row-wise).
 */
void normalize_l2_batch(py::array_t<float> input) {
    auto buf = input.request();
    if (buf.ndim != 2) throw std::runtime_error("Input must be 2D");
    
    float* ptr = static_cast<float*>(buf.ptr);
    size_t rows = buf.shape[0];
    size_t cols = buf.shape[1];

    for (size_t r = 0; r < rows; ++r) {
        float sum_sq = 0.0f;
        float* row_ptr = ptr + r * cols;
        for (size_t c = 0; c < cols; ++c) {
            sum_sq += row_ptr[c] * row_ptr[c];
        }

        float norm = std::sqrt(sum_sq);
        if (norm > 1e-10f) {
            float inv_norm = 1.0f / norm;
            for (size_t c = 0; c < cols; ++c) {
                row_ptr[c] *= inv_norm;
            }
        }
    }
}

PYBIND11_MODULE(l2norm, m) {
    m.def("normalize_l2", &normalize_l2, "In-place L2 normalization for 1D array");
    m.def("normalize_l2_batch", &normalize_l2_batch, "In-place row-wise L2 normalization for 2D array");
}
