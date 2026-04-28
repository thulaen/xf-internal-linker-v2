#include <pybind11/pybind11.h>
#include <pybind11/numpy.h>
#include <vector>
#include <algorithm>
#include <queue>
#include "include/simsearch_core.h"

namespace py = pybind11;

void cscore_and_topk(const float* destination_ptr, size_t dest_dim, const float* sentence_ptr,
                     size_t num_sentences, size_t sentence_dim, const int32_t* candidate_rows,
                     size_t candidate_count, int top_k, int64_t* out_indices, float* out_scores,
                     size_t* out_count) {
    
    if (candidate_count == 0) {
        *out_count = 0;
        return;
    }

    struct Candidate {
        int64_t index;
        float score;
        bool operator>(const Candidate& other) const { return score > other.score; }
    };

    std::priority_queue<Candidate, std::vector<Candidate>, std::greater<Candidate>> pq;

    for (size_t i = 0; i < candidate_count; ++i) {
        int32_t row_idx = candidate_rows[i];
        if (row_idx < 0 || (size_t)row_idx >= num_sentences) continue;

        const float* sentence = sentence_ptr + ((size_t)row_idx * sentence_dim);
        float dot = 0.0f;
        for (size_t d = 0; d < dest_dim && d < sentence_dim; ++d) {
            dot += destination_ptr[d] * sentence[d];
        }

        pq.push({(int64_t)i, dot});
        if (pq.size() > (size_t)top_k) {
            pq.pop();
        }
    }

    size_t count = pq.size();
    *out_count = count;

    std::vector<Candidate> sorted;
    while (!pq.empty()) {
        sorted.push_back(pq.top());
        pq.pop();
    }
    std::reverse(sorted.begin(), sorted.end());

    for (size_t i = 0; i < count; ++i) {
        out_indices[i] = sorted[i].index;
        out_scores[i] = sorted[i].score;
    }
}

py::tuple score_and_topk(py::array_t<float> destination,
                        py::array_t<float> sentences,
                        py::array_t<int32_t> candidate_rows,
                        int top_k) {
    py::buffer_info d_info = destination.request();
    py::buffer_info s_info = sentences.request();
    py::buffer_info c_info = candidate_rows.request();

    size_t dest_dim = (size_t)d_info.shape[0];
    size_t num_sentences = (size_t)s_info.shape[0];
    size_t sentence_dim = (size_t)s_info.shape[1];
    size_t candidate_count = (size_t)c_info.shape[0];

    std::vector<int64_t> out_indices(top_k);
    std::vector<float> out_scores(top_k);
    size_t out_count = 0;

    cscore_and_topk(
        static_cast<const float*>(d_info.ptr), dest_dim,
        static_cast<const float*>(s_info.ptr), num_sentences, sentence_dim,
        static_cast<const int32_t*>(c_info.ptr), candidate_count,
        top_k, out_indices.data(), out_scores.data(), &out_count
    );

    auto res_indices = py::array_t<int64_t>(out_count);
    auto res_scores = py::array_t<float>(out_count);
    
    std::copy(out_indices.begin(), out_indices.begin() + out_count, (int64_t*)res_indices.request().ptr);
    std::copy(out_scores.begin(), out_scores.begin() + out_count, (float*)res_scores.request().ptr);

    return py::make_tuple(res_indices, res_scores);
}

PYBIND11_MODULE(simsearch, m) {
    m.def("score_and_topk", &score_and_topk, "Score candidates and return top K");
}
