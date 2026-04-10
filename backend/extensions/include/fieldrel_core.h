#pragma once
#include <string>
#include <vector>

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
);
