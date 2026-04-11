#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
namespace py = pybind11;
#endif
#ifdef _WIN32
#define TBB_VERSION_MAJOR 0
#elif !defined(XF_BENCH_MODE) || defined(HAS_TBB)
#include <tbb/parallel_for.h>
#include <tbb/blocked_range.h>
#ifndef TBB_VERSION_MAJOR
#define TBB_VERSION_MAJOR 1
#endif
#else
#define TBB_VERSION_MAJOR 0
#endif
#include <algorithm>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <utility>

#include "include/feedrerank_core.h"

void rerank_factors_core(
    const int32_t* successes, const int32_t* totals,
    const double* exposure_probs,
    size_t count,
    int n_global, double alpha, double beta, double weight,
    double exploration_rate, double* out_factors
) {
    auto compute_one = [&](size_t index) {
        const double score_exploit_raw =
            (static_cast<double>(successes[index]) + alpha) /
            (static_cast<double>(totals[index]) + alpha + beta);
        // Joachims, Swaminathan & Schnabel 2017 (DOI 10.1145/3077136.3080756, eq. 4):
        // blend toward neutral 0.5 for under-exposed pairs (low exposure_prob).
        const double ep = exposure_probs ? exposure_probs[index] : 1.0;
        const double score_exploit = ep * score_exploit_raw + (1.0 - ep) * 0.5;
        const double score_explore =
            exploration_rate *
            std::sqrt(std::log(static_cast<double>(n_global) + 1.0) /
                      (static_cast<double>(totals[index]) + 1.0));
        const double raw_modifier = (score_exploit + score_explore) - 0.5;
        double factor = 1.0 + (weight * raw_modifier);
        factor = std::max(0.5, std::min(2.0, factor));
        out_factors[index] = factor;
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

void mmr_scores_core(
    const double* relevance, size_t candidate_count,
    const double* candidate_ptr, const double* selected_ptr,
    size_t selected_count, size_t embedding_width,
    double diversity_lambda,
    double* mmr_ptr, double* max_sim_ptr
) {
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
            (diversity_lambda * relevance[candidate_index]) -
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

#ifndef XF_BENCH_MODE
py::array_t<double> calculate_rerank_factors_batch(
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> n_successes,
    py::array_t<int32_t, py::array::c_style | py::array::forcecast> n_totals,
    py::array_t<double, py::array::c_style | py::array::forcecast> exposure_probs,
    int n_global,
    double alpha,
    double beta,
    double weight,
    double exploration_rate
) {
    auto successes_buf = n_successes.request();
    auto totals_buf = n_totals.request();
    auto exposure_probs_buf = exposure_probs.request();

    if (successes_buf.ndim != 1 || totals_buf.ndim != 1) {
        throw std::runtime_error("n_successes and n_totals must be 1D int32 arrays");
    }
    if (successes_buf.shape[0] != totals_buf.shape[0]) {
        throw std::runtime_error("n_successes and n_totals must have the same length");
    }
    if (exposure_probs_buf.ndim != 1 || exposure_probs_buf.shape[0] != successes_buf.shape[0]) {
        throw std::runtime_error("exposure_probs must be a 1D float64 array with the same length as n_successes");
    }

    const size_t count = static_cast<size_t>(successes_buf.shape[0]);
    auto factors = py::array_t<double>(count);
    auto factors_buf = factors.request();

    {
        py::gil_scoped_release release;
        rerank_factors_core(
            static_cast<const int32_t*>(successes_buf.ptr),
            static_cast<const int32_t*>(totals_buf.ptr),
            static_cast<const double*>(exposure_probs_buf.ptr),
            count, n_global, alpha, beta, weight, exploration_rate,
            static_cast<double*>(factors_buf.ptr)
        );
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

    auto mmr_scores = py::array_t<double>(candidate_count);
    auto max_similarities = py::array_t<double>(candidate_count);
    auto mmr_buf = mmr_scores.request();
    auto max_sim_buf = max_similarities.request();

    {
        py::gil_scoped_release release;
        mmr_scores_core(
            static_cast<const double*>(relevance_buf.ptr),
            candidate_count,
            static_cast<const double*>(candidate_buf.ptr),
            static_cast<const double*>(selected_buf.ptr),
            selected_count, embedding_width, diversity_lambda,
            static_cast<double*>(mmr_buf.ptr),
            static_cast<double*>(max_sim_buf.ptr)
        );
    }

    return py::make_tuple(mmr_scores, max_similarities);
}

PYBIND11_MODULE(feedrerank, m) {
    m.def(
        "calculate_rerank_factors_batch",
        &calculate_rerank_factors_batch,
        "Calculate rerank factors for aligned success/total/exposure_prob arrays. "
        "exposure_probs must be float64 in [0,1]; 1.0=full signal, 0.0=blend to neutral 0.5 "
        "(Joachims, Swaminathan & Schnabel 2017, DOI 10.1145/3077136.3080756)"
    );
    m.def(
        "calculate_mmr_scores_batch",
        &calculate_mmr_scores_batch,
        "Calculate FR-015 MMR scores and max similarities for a candidate batch"
    );
}
#endif
