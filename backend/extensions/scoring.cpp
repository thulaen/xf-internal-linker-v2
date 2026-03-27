#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <tbb/parallel_for.h>
#include <vector>
#include <algorithm>

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

    return results;
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
}
