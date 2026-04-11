#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py = pybind11;
#endif
#include <cmath>
#include <unordered_map>
#include <vector>

/**
 * Fast C++ Inverted Index for BM25-style keyword matching.
 */
class InvertedIndex {
   public:
    void add_document(int doc_id, const std::vector<uint32_t>& tokens) {
        doc_lengths_[doc_id] = static_cast<float>(tokens.size());
        for (auto token : tokens) {
            index_[token].push_back(doc_id);
        }
        total_docs_++;
        total_doc_length_ += tokens.size();
    }

    std::unordered_map<int, float> search(const std::vector<uint32_t>& query_tokens,
                                          float k1 = 1.5f, float b = 0.75f) {
        std::unordered_map<int, float> scores;
        if (total_docs_ == 0)
            return scores;

        float avg_dl = total_doc_length_ / total_docs_;

        for (auto token : query_tokens) {
            auto it = index_.find(token);
            if (it == index_.end())
                continue;

            const auto& postings = it->second;
            float n_q = static_cast<float>(postings.size());
            float idf = std::log((total_docs_ - n_q + 0.5f) / (n_q + 0.5f) + 1.0f);
            idf = std::max(0.0f, idf);

            // Document frequencies for this token
            std::unordered_map<int, int> f_q;
            for (int doc_id : postings) {
                f_q[doc_id]++;
            }

            for (auto const& [doc_id, freq] : f_q) {
                float f = static_cast<float>(freq);
                float dl = doc_lengths_[doc_id];
                float score = idf * (f * (k1 + 1.0f)) / (f + k1 * (1.0f - b + b * (dl / avg_dl)));
                scores[doc_id] += score;
            }
        }
        return scores;
    }

   private:
    std::unordered_map<uint32_t, std::vector<int>> index_;
    std::unordered_map<int, float> doc_lengths_;
    float total_doc_length_ = 0.0f;
    int total_docs_ = 0;
};

#ifndef XF_BENCH_MODE
PYBIND11_MODULE(inv_index, m) {
    py::class_<InvertedIndex>(m, "InvertedIndex")
        .def(py::init<>())
        .def("add_document", &InvertedIndex::add_document, "Add a document to the index")
        .def("search", &InvertedIndex::search, "Search the index using BM25 scoring");
}
#endif
