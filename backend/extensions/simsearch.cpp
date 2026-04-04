#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <pybind11/stl.h>
#ifdef _WIN32
#define TBB_VERSION_MAJOR 0
#else
#include <tbb/parallel_for.h>
#include <tbb/blocked_range.h>
#endif
#include <algorithm>
#include <numeric>
#include <stdexcept>
#include <vector>

namespace py = pybind11;

std::tuple<py::array_t<int64_t>, py::array_t<float>> score_and_topk(
    py::array_t<float, py::array::c_style | py::array::forcecast> destination_embedding,
    py::array_t<float, py::array::c_style | py::array::forcecast> sentence_embeddings,
    const std::vector<int>& candidate_rows,
    int top_k
) {
    auto destination_buf = destination_embedding.request();
    auto sentence_buf = sentence_embeddings.request();

    if (destination_buf.ndim != 1) {
        throw std::runtime_error("destination_embedding must be a 1D float32 array");
    }
    if (sentence_buf.ndim != 2) {
        throw std::runtime_error("sentence_embeddings must be a 2D float32 array");
    }
    if (sentence_buf.shape[1] != destination_buf.shape[0]) {
        throw std::runtime_error("sentence_embeddings.shape[1] must match destination_embedding.shape[0]");
    }
    if (top_k <= 0 || candidate_rows.empty()) {
        return std::make_tuple(py::array_t<int64_t>(0), py::array_t<float>(0));
    }

    const auto row_count = static_cast<size_t>(sentence_buf.shape[0]);
    const auto dimension = static_cast<size_t>(sentence_buf.shape[1]);
    const auto candidate_count = candidate_rows.size();
    const auto* destination_ptr = static_cast<const float*>(destination_buf.ptr);
    const auto* sentence_ptr = static_cast<const float*>(sentence_buf.ptr);

    std::vector<float> scores(candidate_count, 0.0f);
    {
        py::gil_scoped_release release;

        auto compute_one = [&](size_t candidate_index) {
            const int row_index = candidate_rows[candidate_index];
            if (row_index < 0 || static_cast<size_t>(row_index) >= row_count) {
                throw std::runtime_error("candidate row index out of bounds");
            }
            const size_t offset = static_cast<size_t>(row_index) * dimension;
            double total = 0.0;
            for (size_t dim = 0; dim < dimension; ++dim) {
                total += static_cast<double>(sentence_ptr[offset + dim]) *
                         static_cast<double>(destination_ptr[dim]);
            }
            scores[candidate_index] = static_cast<float>(total);
        };

        if (candidate_count > 256) {
#if TBB_VERSION_MAJOR > 0
            tbb::parallel_for(
                tbb::blocked_range<size_t>(0, static_cast<size_t>(candidate_count)),
                [&](const tbb::blocked_range<size_t>& range) {
                    for (size_t index = range.begin(); index < range.end(); ++index) {
                        compute_one(index);
                    }
                }
            );
#else
            for (size_t index = 0; index < static_cast<size_t>(candidate_count); ++index) {
                compute_one(index);
            }
#endif
        } else {
            for (size_t index = 0; index < static_cast<size_t>(candidate_count); ++index) {
                compute_one(index);
            }
        }
    }

    const size_t keep_count = std::min(static_cast<size_t>(top_k), static_cast<size_t>(candidate_count));
    std::vector<int64_t> positions(candidate_count);
    std::iota(positions.begin(), positions.end(), static_cast<int64_t>(0));

    auto compare_positions = [&](int64_t left, int64_t right) {
        return scores[static_cast<size_t>(left)] > scores[static_cast<size_t>(right)];
    };

    if (keep_count < positions.size()) {
        std::nth_element(
            positions.begin(),
            positions.begin() + static_cast<std::ptrdiff_t>(keep_count),
            positions.end(),
            compare_positions
        );
    }
    positions.resize(keep_count);
    std::sort(positions.begin(), positions.end(), compare_positions);

    auto out_indices = py::array_t<int64_t>(keep_count);
    auto out_scores = py::array_t<float>(keep_count);
    auto indices_buf = out_indices.request();
    auto scores_buf = out_scores.request();
    auto* indices_ptr = static_cast<int64_t*>(indices_buf.ptr);
    auto* out_scores_ptr = static_cast<float*>(scores_buf.ptr);

    for (size_t i = 0; i < keep_count; ++i) {
        indices_ptr[i] = positions[i];
        out_scores_ptr[i] = scores[static_cast<size_t>(positions[i])];
    }

    return std::make_tuple(out_indices, out_scores);
}

PYBIND11_MODULE(simsearch, m) {
    m.def(
        "score_and_topk",
        &score_and_topk,
        "Score candidate sentence rows and return top-K positional indices with scores"
    );
}

extern "C" {
#ifdef _WIN32
    __declspec(dllexport)
#else
    __attribute__((visibility("default")))
#endif
    void cscore_and_topk(
        const float* destination_ptr, size_t dest_dim,
        const float* sentence_ptr, size_t num_sentences, size_t sentence_dim,
        const int32_t* candidate_rows, size_t candidate_count,
        int top_k,
        int64_t* out_indices, float* out_scores, size_t* out_count
    ) {
        if (dest_dim != sentence_dim) {
            *out_count = 0;
            return;
        }
        if (top_k <= 0 || candidate_count == 0) {
            *out_count = 0;
            return;
        }

        std::vector<float> scores(candidate_count, 0.0f);
        auto compute_one = [&](size_t candidate_index) {
            int32_t row_index = candidate_rows[candidate_index];
            if (row_index < 0 || static_cast<size_t>(row_index) >= num_sentences) {
                return;
            }
            size_t offset = static_cast<size_t>(row_index) * sentence_dim;
            double total = 0.0;
            for (size_t dim = 0; dim < sentence_dim; ++dim) {
                total += static_cast<double>(sentence_ptr[offset + dim]) *
                         static_cast<double>(destination_ptr[dim]);
            }
            scores[candidate_index] = static_cast<float>(total);
        };

        if (candidate_count > 256) {
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

        size_t keep_count = std::min(static_cast<size_t>(top_k), candidate_count);
        *out_count = keep_count;
        std::vector<int64_t> positions(candidate_count);
        std::iota(positions.begin(), positions.end(), static_cast<int64_t>(0));

        auto compare_positions = [&](int64_t left, int64_t right) {
            return scores[static_cast<size_t>(left)] > scores[static_cast<size_t>(right)];
        };

        if (keep_count < positions.size()) {
            std::nth_element(
                positions.begin(),
                positions.begin() + static_cast<std::ptrdiff_t>(keep_count),
                positions.end(),
                compare_positions
            );
        }
        std::sort(positions.begin(), positions.begin() + static_cast<std::ptrdiff_t>(keep_count), compare_positions);

        for (size_t i = 0; i < keep_count; ++i) {
            out_indices[i] = positions[i];
            out_scores[i] = scores[static_cast<size_t>(positions[i])];
        }
    }
}
