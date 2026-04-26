#ifndef XF_BENCH_MODE
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
namespace py = pybind11;
#endif
#ifdef _WIN32
#define TBB_VERSION_MAJOR 0
#elif !defined(XF_BENCH_MODE) || defined(HAS_TBB)
#include <tbb/blocked_range.h>
#include <tbb/parallel_for.h>
#ifndef TBB_VERSION_MAJOR
#define TBB_VERSION_MAJOR 1
#endif
#else
#define TBB_VERSION_MAJOR 0
#endif
#include <algorithm>
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <stdexcept>
#include <utility>

#include "include/feedrerank_core.h"

void rerank_factors_core(const int32_t *successes, const int32_t *totals,
                         const double *observation_confidences, size_t count,
                         int n_global, double alpha, double beta, double weight,
                         double exploration_rate, double *out_factors) {
  auto compute_one = [&](size_t index) {
    // PARITY: matches feedback_rerank.py line 155-158 — Bayesian exploit
    // numerator with 1e-9 denominator guard. The guard is dormant under
    // the default alpha=beta=1 priors (denom >= 2) but activates when an
    // operator zeroes both priors AND totals is zero: without it the
    // division produces NaN/Infinity and the C++ factor diverges from the
    // Python reference. Closes RPT-001 Finding 3.
    const double exploit_denom =
        static_cast<double>(totals[index]) + alpha + beta;
    const double score_exploit_raw =
        (static_cast<double>(successes[index]) + alpha) /
        std::max(exploit_denom, 1e-9);
    // PARITY: matches feedback_rerank.py lines 177-181 — linear
    // observation_confidence blend toward neutral 0.5. This is NOT
    // an inverse-propensity estimator (see RPT-001 Finding 2 resolved
    // 2026-04-20). Joachims, Swaminathan & Schnabel 2017 (DOI
    // 10.1145/3077136.3080756) is kept as inspiration only; a per-event
    // propensity model would require per-event impression storage the
    // system does not currently maintain.
    const double oc =
        observation_confidences ? observation_confidences[index] : 1.0;
    const double score_exploit = oc * score_exploit_raw + (1.0 - oc) * 0.5;
    // PARITY: matches feedback_rerank.py line 166 — UCB1 explore
    const double score_explore =
        exploration_rate *
        std::sqrt(std::log(static_cast<double>(n_global) + 1.0) /
                  (static_cast<double>(totals[index]) + 1.0));
    // PARITY: matches feedback_rerank.py line 173 — combined modifier
    const double raw_modifier = (score_exploit + score_explore) - 0.5;
    // PARITY: matches feedback_rerank.py line 174 — weighted factor
    double factor = 1.0 + (weight * raw_modifier);
    // PARITY: matches feedback_rerank.py line 177 — clamp to [0.5, 2.0]
    factor = std::max(0.5, std::min(2.0, factor));
#ifndef NDEBUG
    assert(factor >= 0.5 && factor <= 2.0 &&
           "rerank factor out of clamp range");
#endif
    out_factors[index] = factor;
  };

  if (count > 256) {
#if TBB_VERSION_MAJOR > 0
    tbb::parallel_for(tbb::blocked_range<size_t>(0, count),
                      [&](const tbb::blocked_range<size_t> &range) {
                        for (size_t index = range.begin(); index < range.end();
                             ++index) {
                          compute_one(index);
                        }
                      });
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

void mmr_scores_core(const double *relevance, size_t candidate_count,
                     const double *candidate_ptr, const double *selected_ptr,
                     size_t selected_count, size_t embedding_width,
                     double diversity_lambda, double *mmr_ptr,
                     double *max_sim_ptr) {
  auto compute_one = [&](size_t candidate_index) {
    const auto *candidate_row =
        candidate_ptr + (candidate_index * embedding_width);
    double max_similarity = 0.0;

    for (size_t selected_index = 0; selected_index < selected_count;
         ++selected_index) {
      const auto *selected_row =
          selected_ptr + (selected_index * embedding_width);
      double dot = 0.0;
      for (size_t dim = 0; dim < embedding_width; ++dim) {
        dot += candidate_row[dim] * selected_row[dim];
      }
      if (selected_index == 0 || dot > max_similarity) {
        max_similarity = dot;
      }
    }

    max_sim_ptr[candidate_index] = max_similarity;
    mmr_ptr[candidate_index] = (diversity_lambda * relevance[candidate_index]) -
                               ((1.0 - diversity_lambda) * max_similarity);
  };

  if (candidate_count > 128) {
#if TBB_VERSION_MAJOR > 0
    tbb::parallel_for(tbb::blocked_range<size_t>(0, candidate_count),
                      [&](const tbb::blocked_range<size_t> &range) {
                        for (size_t index = range.begin(); index < range.end();
                             ++index) {
                          compute_one(index);
                        }
                      });
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
    py::array_t<double, py::array::c_style | py::array::forcecast>
        observation_confidences,
    int n_global, double alpha, double beta, double weight,
    double exploration_rate) {
  auto successes_buf = n_successes.request();
  auto totals_buf = n_totals.request();
  auto observation_confidences_buf = observation_confidences.request();

  if (successes_buf.ndim != 1 || totals_buf.ndim != 1) {
    throw std::runtime_error(
        "n_successes and n_totals must be 1D int32 arrays");
  }
  if (successes_buf.shape[0] != totals_buf.shape[0]) {
    throw std::runtime_error(
        "n_successes and n_totals must have the same length");
  }
  if (observation_confidences_buf.ndim != 1 ||
      observation_confidences_buf.shape[0] != successes_buf.shape[0]) {
    throw std::runtime_error("observation_confidences must be a 1D float64 "
                             "array with the same length as "
                             "n_successes");
  }

  const size_t count = static_cast<size_t>(successes_buf.shape[0]);
  auto factors = py::array_t<double>(count);
  auto factors_buf = factors.request();

  {
    py::gil_scoped_release release;
    rerank_factors_core(
        static_cast<const int32_t *>(successes_buf.ptr),
        static_cast<const int32_t *>(totals_buf.ptr),
        static_cast<const double *>(observation_confidences_buf.ptr), count,
        n_global, alpha, beta, weight, exploration_rate,
        static_cast<double *>(factors_buf.ptr));
  }

  return factors;
}

py::tuple calculate_mmr_scores_batch(
    py::array_t<double, py::array::c_style | py::array::forcecast> relevance,
    py::array_t<double, py::array::c_style | py::array::forcecast>
        candidate_embeddings,
    py::array_t<double, py::array::c_style | py::array::forcecast>
        selected_embeddings,
    double diversity_lambda) {
  auto relevance_buf = relevance.request();
  auto candidate_buf = candidate_embeddings.request();
  auto selected_buf = selected_embeddings.request();

  if (relevance_buf.ndim != 1) {
    throw std::runtime_error("relevance must be a 1D float array");
  }
  if (candidate_buf.ndim != 2 || selected_buf.ndim != 2) {
    throw std::runtime_error(
        "candidate_embeddings and selected_embeddings must be 2D float arrays");
  }
  if (candidate_buf.shape[0] != relevance_buf.shape[0]) {
    throw std::runtime_error(
        "candidate_embeddings rows must match relevance length");
  }
  if (candidate_buf.shape[1] != selected_buf.shape[1]) {
    throw std::runtime_error("candidate_embeddings and selected_embeddings "
                             "must have the same embedding width");
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
        static_cast<const double *>(relevance_buf.ptr), candidate_count,
        static_cast<const double *>(candidate_buf.ptr),
        static_cast<const double *>(selected_buf.ptr), selected_count,
        embedding_width, diversity_lambda, static_cast<double *>(mmr_buf.ptr),
        static_cast<double *>(max_sim_buf.ptr));
  }

  return py::make_tuple(mmr_scores, max_similarities);
}

PYBIND11_MODULE(feedrerank, m) {
  m.def("calculate_rerank_factors_batch", &calculate_rerank_factors_batch,
        "Calculate rerank factors for aligned "
        "(n_successes, n_totals, observation_confidences) arrays. "
        "observation_confidences must be float64 in [0,1]; 1.0=full exploit "
        "signal, "
        "0.0=blend to neutral 0.5. This is a linear confidence blend — NOT an "
        "inverse-propensity estimator (see RPT-001 Finding 2). Joachims, "
        "Swaminathan "
        "& Schnabel 2017 (DOI 10.1145/3077136.3080756) inspired the naming but "
        "the "
        "per-event IPS guarantee is not implemented.");
  m.def(
      "calculate_mmr_scores_batch", &calculate_mmr_scores_batch,
      "Calculate FR-015 MMR scores and max similarities for a candidate batch");
}
#endif
