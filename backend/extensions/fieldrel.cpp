#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <algorithm>
#include <cmath>
#include <stdexcept>
#include <string>
#include <tuple>
#include <vector>

namespace py = pybind11;

double score_field_tokens(
    const std::vector<std::string>& tokens,
    const std::vector<int>& host_tfs,
    const std::vector<int>& field_tfs,
    const std::vector<int>& field_presence_counts,
    int field_length,
    double reference_length,
    double b_value,
    int field_count,
    double bm25_k1,
    int max_matched
) {
    const size_t token_count = tokens.size();
    if (host_tfs.size() != token_count || field_tfs.size() != token_count ||
        field_presence_counts.size() != token_count) {
        throw std::runtime_error("All token lists must be positionally aligned and the same length");
    }
    if (token_count == 0 || max_matched <= 0) {
        return 0.0;
    }

    struct ScoredToken {
        std::string token;
        int field_tf;
        double token_score;
    };

    std::vector<ScoredToken> scored_tokens;
    scored_tokens.reserve(token_count);

    for (size_t index = 0; index < token_count; ++index) {
        const double idf = std::log1p(
            (1.0 + static_cast<double>(field_count)) /
            (1.0 + static_cast<double>(field_presence_counts[index]))
        );
        const double denominator =
            static_cast<double>(field_tfs[index]) +
            bm25_k1 * (
                1.0 - b_value +
                b_value * (static_cast<double>(field_length) / std::max(1.0, reference_length))
            );
        const double tf_norm = denominator > 0.0
            ? (static_cast<double>(field_tfs[index]) * (bm25_k1 + 1.0)) / denominator
            : 0.0;
        const double token_score = tf_norm * idf * std::min(2.0, static_cast<double>(host_tfs[index]));
        scored_tokens.push_back({tokens[index], field_tfs[index], token_score});
    }

    std::sort(
        scored_tokens.begin(),
        scored_tokens.end(),
        [](const ScoredToken& left, const ScoredToken& right) {
            if (left.token_score != right.token_score) {
                return left.token_score > right.token_score;
            }
            if (left.field_tf != right.field_tf) {
                return left.field_tf > right.field_tf;
            }
            return left.token < right.token;
        }
    );

    const size_t keep_count = std::min(static_cast<size_t>(max_matched), scored_tokens.size());
    double field_raw = 0.0;
    for (size_t index = 0; index < keep_count; ++index) {
        field_raw += scored_tokens[index].token_score;
    }
    field_raw /= static_cast<double>(keep_count);
    return field_raw / (1.0 + field_raw);
}

PYBIND11_MODULE(fieldrel, m) {
    m.def(
        "score_field_tokens",
        &score_field_tokens,
        "Score aligned field tokens where index i refers to the same token in tokens, host_tfs, field_tfs, and field_presence_counts"
    );
}
