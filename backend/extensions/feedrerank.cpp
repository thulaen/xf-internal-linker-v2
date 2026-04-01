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

PYBIND11_MODULE(feedrerank, m) {
    m.def(
        "calculate_rerank_factors_batch",
        &calculate_rerank_factors_batch,
        "Calculate rerank factors for aligned success and total count arrays"
    );
}
