#pragma once
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

std::pair<bool, double> evaluate_rare_terms_core(
    const std::vector<std::string>& terms, const std::vector<double>& term_evidences,
    const std::vector<int>& supporting_pages, const std::unordered_set<std::string>& host_token_set,
    int max_terms);
