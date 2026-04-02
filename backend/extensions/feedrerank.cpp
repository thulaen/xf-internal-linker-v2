#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#ifdef _WIN32
#define TBB_VERSION_MAJOR 0
#else
#include <tbb/parallel_for.h>
#include <tbb/blocked_range.h>
#endif
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <utility>

namespace py = pybind11;

py::array_t<double> calculate_rerank_factors_batch(
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> n_successes,
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> n_totals,
    int n_global,
    double alpha,
    double beta,
    double weight,
    double exploration_rate
) {
    auto successes_buf = n_successes.request();
    auto totals_buf = n_totals.request();

    if (successes_buf.ndim != 1 || totals_buf.ndim != 1) {
        throw std::runtime_error("n_successes and n_totals must be 1D int32 arrays");
    }
    if (successes_buf.shape[0] != totals_buf.shape[0]) {
        throw std::runtime_error("n_successes and n_totals must have the same length");
    }

    const size_t count = static_cast<size_t>(successes_buf.shape[0]);
    const auto* successes_ptr = static_cast<const int32_t*>(successes_buf.ptr);
    const auto* totals_ptr = static_cast<const int32_t*>(totals_buf.ptr);

    auto factors = py::array_t<double>(count);
    auto factors_buf = factors.request();
    auto* factors_ptr = static_cast<double*>(factors_buf.ptr);

    {
        py::gil_scoped_release release;

        auto compute_one = [&](size_t index) {
            const double score_exploit =
                (static_cast<double>(successes_ptr[index]) + alpha) /
                (static_cast<double>(totals_ptr[index]) + alpha + beta);
            const double score_explore =
                exploration_rate *
                std::sqrt(std::log(static_cast<double>(n_global) + 1.0) /
                          (static_cast<double>(totals_ptr[index]) + 1.0));
            const double raw_modifier = (score_exploit + score_explore) - 0.5;
            double factor = 1.0 + (weight * raw_modifier);
            factor = std::max(0.5, std::min(2.0, factor));
            factors_ptr[index] = factor;
        };

        if (count > 256) {
#if TBB_VERSION_MAJOR > 0
            tbb::parallel_for(
                tbb::blocked_range<size_t>(0, count),
                [&](const tbb::blocked_range<size_t>& range) {
                    for (size_t index = range.begin(); index < range.end(); ++index) {
                        compute_one(index);
                    }
                }
            );
#else
            for (size_t index = 0; index < count; ++index) {
                compute_one(index);
            }
#endif
        } else {
            for (size_t index = 0; index < count; ++index) {
                compute_one(index);
            }
        }
    }

    return factors;
}

py::tuple calculate_mmr_scores_batch(
    py::array_t<double, py::array::c_style | py::array::forcecast> relevance,
    py::array_t<double, py::array::c_style | py::array::forcecast> candidate_embeddings,
    py::array_t<double, py::array::c_style | py::array::forcecast> selected_embeddings,
    double diversity_lambda
) {
    auto relevance_buf = relevance.request();
    auto candidate_buf = candidate_embeddings.request();
    auto selected_buf = selected_embeddings.request();

    if (relevance_buf.ndim != 1) {
        throw std::runtime_error("relevance must be a 1D float array");
    }
    if (candidate_buf.ndim != 2 || selected_buf.ndim != 2) {
        throw std::runtime_error("candidate_embeddings and selected_embeddings must be 2D float arrays");
    }
    if (candidate_buf.shape[0] != relevance_buf.shape[0]) {
        throw std::runtime_error("candidate_embeddings rows must match relevance length");
    }
    if (candidate_buf.shape[1] != selected_buf.shape[1]) {
        throw std::runtime_error("candidate_embeddings and selected_embeddings must have the same embedding width");
    }

    const auto candidate_count = static_cast<size_t>(candidate_buf.shape[0]);
    const auto selected_count = static_cast<size_t>(selected_buf.shape[0]);
    const auto embedding_width = static_cast<size_t>(candidate_buf.shape[1]);

    const auto* relevance_ptr = static_cast<const double*>(relevance_buf.ptr);
    const auto* candidate_ptr = static_cast<const double*>(candidate_buf.ptr);
    const auto* selected_ptr = static_cast<const double*>(selected_buf.ptr);

    auto mmr_scores = py::array_t<double>(candidate_count);
    auto max_similarities = py::array_t<double>(candidate_count);
    auto mmr_buf = mmr_scores.request();
    auto max_sim_buf = max_similarities.request();
    auto* mmr_ptr = static_cast<double*>(mmr_buf.ptr);
    auto* max_sim_ptr = static_cast<double*>(max_sim_buf.ptr);

    {
        py::gil_scoped_release release;

        auto compute_one = [&](size_t candidate_index) {
            const auto* candidate_row = candidate_ptr + (candidate_index * embedding_width);
            double max_similarity = 0.0;

            for (size_t selected_index = 0; selected_index < selected_count; ++selected_index) {
                const auto* selected_row = selected_ptr + (selected_index * embedding_width);
                double dot = 0.0;
                for (size_t dim = 0; dim < embedding_width; ++dim) {
                    dot += candidate_row[dim] * selected_row[dim];
                }
                if (selected_index == 0 || dot > max_similarity) {
                    max_similarity = dot;
                }
            }

            max_sim_ptr[candidate_index] = max_similarity;
            mmr_ptr[candidate_index] =
                (diversity_lambda * relevance_ptr[candidate_index]) -
                ((1.0 - diversity_lambda) * max_similarity);
        };

        if (candidate_count > 128) {
#if TBB_VERSION_MAJOR > 0
            tbb::parallel_for(
                tbb::blocked_range<size_t>(0, candidate_count),
                [&](const tbb::blocked_range<size_t>& range) {
                    for (size_t index = range.begin(); index < range.end(); ++index) {
                        compute_one(index);
                    }
                }
            );
#else
            for (size_t index = 0; index < candidate_count; ++index) {
                compute_one(index);
            }
#endif
        } else {
            for (size_t index = 0; index < candidate_count; ++index) {
                compute_one(index);
            }
        }
    }

    return py::make_tuple(mmr_scores, max_similarities);
}

PYBIND11_MODULE(feedrerank, m) {
    m.def(
        "calculate_rerank_factors_batch",
        &calculate_rerank_factors_batch,
        "Calculate rerank factors for aligned success and total count arrays"
    );
    m.def(
        "calculate_mmr_scores_batch",
        &calculate_mmr_scores_batch,
        "Calculate FR-015 MMR scores and max similarities for a candidate batch"
    );
}
