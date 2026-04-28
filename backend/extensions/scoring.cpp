#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <vector>
#include "include/scoring_core.h"

namespace py = pybind11;

void cscore_full_batch(const float* component_scores, size_t num_rows, size_t num_components,
                       const float* weights, size_t num_weights, const float* silo_scores,
                       size_t num_silo, float* out_scores) {
    for (size_t i = 0; i < num_rows; ++i) {
        float sum = 0.0f;
        if (silo_scores && i < num_silo) {
            sum = silo_scores[i];
        }
        
        const float* row = component_scores + (i * num_components);
        for (size_t j = 0; j < num_components && j < num_weights; ++j) {
            sum += row[j] * weights[j];
        }
        out_scores[i] = sum;
    }
}

py::array_t<float> score_full_batch(py::array_t<float> component_scores,
                                   py::array_t<float> weights,
                                   py::array_t<float> silo_scores) {
    py::buffer_info c_info = component_scores.request();
    py::buffer_info w_info = weights.request();
    py::buffer_info s_info = silo_scores.request();

    size_t num_rows = (size_t)c_info.shape[0];
    size_t num_components = (size_t)c_info.shape[1];
    size_t num_weights = (size_t)w_info.shape[0];
    size_t num_silo = (size_t)s_info.shape[0];

    auto result = py::array_t<float>(num_rows);
    py::buffer_info res_info = result.request();

    cscore_full_batch(
        static_cast<const float*>(c_info.ptr), num_rows, num_components,
        static_cast<const float*>(w_info.ptr), num_weights,
        static_cast<const float*>(s_info.ptr), num_silo,
        static_cast<float*>(res_info.ptr)
    );

    return result;
}

PYBIND11_MODULE(scoring, m) {
    m.def("score_full_batch", &score_full_batch, "Compute final scores for a batch");
}
