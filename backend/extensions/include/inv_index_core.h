#pragma once
#include <cmath>
#include <cstdint>
#include <unordered_map>
#include <vector>

#ifdef XF_BENCH_MODE
/* Full class definition so benchmarks can link against inline methods */
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

    std::unordered_map<int, float> search(
        const std::vector<uint32_t>& query_tokens,
        float k1 = 1.5f,
        float b = 0.75f
    ) {
        std::unordered_map<int, float> scores;
        if (total_docs_ == 0) return scores;

        float avg_dl = total_doc_length_ / total_docs_;

        for (auto token : query_tokens) {
            auto it = index_.find(token);
            if (it == index_.end()) continue;

            const auto& postings = it->second;
            float n_q = static_cast<float>(postings.size());
            float idf = std::log((total_docs_ - n_q + 0.5f) / (n_q + 0.5f) + 1.0f);
            idf = std::max(0.0f, idf);

            std::unordered_map<int, int> f_q;
            for (int did : postings) {
                f_q[did]++;
            }

            for (auto const& [did, freq] : f_q) {
                float f = static_cast<float>(freq);
                float dl = doc_lengths_[did];
                float score = idf * (f * (k1 + 1.0f)) /
                    (f + k1 * (1.0f - b + b * (dl / avg_dl)));
                scores[did] += score;
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
#endif
