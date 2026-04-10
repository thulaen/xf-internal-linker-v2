#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
namespace py = pybind11;
#endif
#include <cmath>
#include <vector>
#include <numeric>
#ifdef _WIN32
#include <execution>
#include <algorithm>
#define HAS_PAR_EXECUTION 1
#endif

#include "include/l2norm_core.h"

void l2norm_normalize(float* ptr, size_t size) {
    if (size == 0) return;

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

void l2norm_normalize_batch(float* ptr, size_t rows, size_t cols) {
    if (rows == 0 || cols == 0) return;

#if defined(HAS_PAR_EXECUTION)
    std::vector<size_t> indices(rows);
    std::iota(indices.begin(), indices.end(), 0);
    std::for_each(std::execution::par, indices.begin(), indices.end(), [&](size_t r) {
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
    });
#else
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
#endif
}

#ifndef XF_BENCH_MODE
void normalize_l2(py::array_t<float, py::array::c_style | py::array::forcecast> input) {
    auto buf = input.request();
    if (buf.size == 0) return;
    l2norm_normalize(static_cast<float*>(buf.ptr), static_cast<size_t>(buf.size));
}

void normalize_l2_batch(py::array_t<float, py::array::c_style | py::array::forcecast> input) {
    auto buf = input.request();
    if (buf.ndim != 2) throw std::runtime_error("Input must be 2D");
    l2norm_normalize_batch(
        static_cast<float*>(buf.ptr),
        static_cast<size_t>(buf.shape[0]),
        static_cast<size_t>(buf.shape[1])
    );
}

PYBIND11_MODULE(l2norm, m) {
    m.def("normalize_l2", &normalize_l2, "In-place L2 normalization for 1D array");
    m.def("normalize_l2_batch", &normalize_l2_batch, "In-place row-wise L2 normalization for 2D array");
}
#endif
