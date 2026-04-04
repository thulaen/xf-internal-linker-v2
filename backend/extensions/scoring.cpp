#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#ifdef _WIN32
#include <execution>
#include <algorithm>
#define HAS_PAR_EXECUTION 1
#else
#include <tbb/parallel_for.h>
#include <tbb/blocked_range.h>
#define HAS_TBB 1
#endif
#include <numeric>
#include <vector>
#include <stdexcept>

#include <vector>
#include <stdexcept>

namespace py = pybind11;

/**
 * Parallel composite scoring for suggestions.
 * Uses TBB for multi-core scaling.
 */
struct Candidate {
    float score_semantic;
    float score_keyword;
    float score_node;
    float score_quality;
    float score_pr;
    float score_freshness;
    float score_ga4;

    Candidate(float s, float k, float n, float q, float p, float f, float g)
        : score_semantic(s), score_keyword(k), score_node(n), score_quality(q), 
          score_pr(p), score_freshness(f), score_ga4(g) {}
};

std::vector<float> calculate_composite_scores(
    const std::vector<Candidate>& candidates,
    float w_semantic,
    float w_keyword,
    float w_node,
    float w_quality,
    float w_pr,
    float w_freshness,
    float w_ga4
) {
    std::vector<float> results(candidates.size());

    py::gil_scoped_release release;
#if defined(HAS_PAR_EXECUTION)
    std::vector<size_t> indices(candidates.size());
    std::iota(indices.begin(), indices.end(), 0);
    std::for_each(std::execution::par, indices.begin(), indices.end(), [&](size_t i) {
        const auto& c = candidates[i];
        results[i] = (c.score_semantic * w_semantic) +
                     (c.score_keyword * w_keyword) +
                     (c.score_node * w_node) +
                     (c.score_quality * w_quality) +
                     (c.score_pr * w_pr) +
                     (c.score_freshness * w_freshness) +
                     (c.score_ga4 * w_ga4);
    });
#elif defined(HAS_TBB)
    tbb::parallel_for(tbb::blocked_range<size_t>(0, candidates.size()),
        [&](const tbb::blocked_range<size_t>& r) {
            for (size_t i = r.begin(); i < r.end(); ++i) {
                const auto& c = candidates[i];
                results[i] = (c.score_semantic * w_semantic) +
                             (c.score_keyword * w_keyword) +
                             (c.score_node * w_node) +
                             (c.score_quality * w_quality) +
                             (c.score_pr * w_pr) +
                             (c.score_freshness * w_freshness) +
                             (c.score_ga4 * w_ga4);
            }
        });
#else
    for (size_t i = 0; i < candidates.size(); ++i) {
        const auto& c = candidates[i];
        results[i] = (c.score_semantic * w_semantic) +
                     (c.score_keyword * w_keyword) +
                     (c.score_node * w_node) +
                     (c.score_quality * w_quality) +
                     (c.score_pr * w_pr) +
                     (c.score_freshness * w_freshness) +
                     (c.score_ga4 * w_ga4);
    }
#endif

    return results;
}

py::array_t<float> calculate_composite_scores_full_batch(
    py::array_t<float, py::array::c_style | py::array::forcecast> component_scores,
    py::array_t<float, py::array::c_style | py::array::forcecast> weights,
    py::array_t<float, py::array::c_style | py::array::forcecast> silo
) {
    auto component_buf = component_scores.request();
    auto weight_buf = weights.request();
    auto silo_buf = silo.request();

    if (component_buf.ndim != 2) {
        throw std::runtime_error("component_scores must be a 2D float32 array");
    }
    if (weight_buf.ndim != 1) {
        throw std::runtime_error("weights must be a 1D float32 array");
    }
    if (silo_buf.ndim != 1) {
        throw std::runtime_error("silo must be a 1D float32 array");
    }

    const auto n_rows = static_cast<size_t>(component_buf.shape[0]);
    const auto k_components = static_cast<size_t>(component_buf.shape[1]);

    if (static_cast<size_t>(weight_buf.shape[0]) != k_components) {
        throw std::runtime_error("weights length must match component_scores.shape[1]");
    }
    if (static_cast<size_t>(silo_buf.shape[0]) != n_rows) {
        throw std::runtime_error("silo length must match component_scores.shape[0]");
    }

    const auto* component_ptr = static_cast<const float*>(component_buf.ptr);
    const auto* weight_ptr = static_cast<const float*>(weight_buf.ptr);
    const auto* silo_ptr = static_cast<const float*>(silo_buf.ptr);

    auto result = py::array_t<float>(n_rows);
    auto result_buf = result.request();
    auto* result_ptr = static_cast<float*>(result_buf.ptr);

    {
        py::gil_scoped_release release;
#if defined(HAS_PAR_EXECUTION)
        std::vector<size_t> indices(n_rows);
        std::iota(indices.begin(), indices.end(), 0);
        std::for_each(std::execution::par, indices.begin(), indices.end(), [&](size_t row) {
            const size_t offset = row * k_components;
            float total = silo_ptr[row];
            for (size_t col = 0; col < k_components; ++col) {
                total += component_ptr[offset + col] * weight_ptr[col];
            }
            result_ptr[row] = total;
        });
#elif defined(HAS_TBB)
        tbb::parallel_for(tbb::blocked_range<size_t>(0, n_rows),
            [&](const tbb::blocked_range<size_t>& r) {
                for (size_t row = r.begin(); row < r.end(); ++row) {
                    const size_t offset = row * k_components;
                    float total = silo_ptr[row];
                    for (size_t col = 0; col < k_components; ++col) {
                        total += component_ptr[offset + col] * weight_ptr[col];
                    }
                    result_ptr[row] = total;
                }
            });
#else
        for (size_t row = 0; row < n_rows; ++row) {
            const size_t offset = row * k_components;
            float total = silo_ptr[row];
            for (size_t col = 0; col < k_components; ++col) {
                total += component_ptr[offset + col] * weight_ptr[col];
            }
            result_ptr[row] = total;
        }
#endif
    }

    return result;
}

PYBIND11_MODULE(scoring, m) {
    py::class_<Candidate>(m, "Candidate")
        .def(py::init<float, float, float, float, float, float, float>())
        .def_readwrite("score_semantic", &Candidate::score_semantic)
        .def_readwrite("score_keyword", &Candidate::score_keyword)
        .def_readwrite("score_node", &Candidate::score_node)
        .def_readwrite("score_quality", &Candidate::score_quality)
        .def_readwrite("score_pr", &Candidate::score_pr)
        .def_readwrite("score_freshness", &Candidate::score_freshness)
        .def_readwrite("score_ga4", &Candidate::score_ga4);

    m.def("calculate_composite_scores", &calculate_composite_scores, "Calculate composite scores in parallel");
    m.def(
        "calculate_composite_scores_full_batch",
        &calculate_composite_scores_full_batch,
        "Calculate batch composite scores from per-row components plus silo adjustments"
    );
}

extern "C" {
#ifdef _WIN32
    __declspec(dllexport)
#else
    __attribute__((visibility("default")))
#endif
    void cscore_full_batch(
        const float* component_scores, size_t num_rows, size_t num_components,
        const float* weights, size_t num_weights,
        const float* silo_scores, size_t num_silo,
        float* out_scores
    ) {
        if (num_components != num_weights || num_rows != num_silo) {
            return;
        }

#if defined(HAS_PAR_EXECUTION)
        std::vector<size_t> indices(num_rows);
        std::iota(indices.begin(), indices.end(), 0);
        std::for_each(std::execution::par, indices.begin(), indices.end(), [&](size_t row) {
            size_t offset = row * num_components;
            float total = silo_scores[row];
            for (size_t col = 0; col < num_components; ++col) {
                total += component_scores[offset + col] * weights[col];
            }
            out_scores[row] = total;
        });
#elif defined(HAS_TBB)
        tbb::parallel_for(
            tbb::blocked_range<size_t>(0, num_rows),
            [&](const tbb::blocked_range<size_t>& range) {
                for (size_t row = range.begin(); row < range.end(); ++row) {
                    size_t offset = row * num_components;
                    float total = silo_scores[row];
                    for (size_t col = 0; col < num_components; ++col) {
                        total += component_scores[offset + col] * weights[col];
                    }
                    out_scores[row] = total;
                }
            }
        );
#else
        for (size_t row = 0; row < num_rows; ++row) {
            size_t offset = row * num_components;
            float total = silo_scores[row];
            for (size_t col = 0; col < num_components; ++col) {
                total += component_scores[offset + col] * weights[col];
            }
            out_scores[row] = total;
        }
#endif
    }
}
