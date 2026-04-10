#pragma once
#include <string>
#include <unordered_set>
#include <vector>

std::unordered_set<std::string> tokenize_one_core(
    const std::string& text,
    const std::unordered_set<std::string>& stopwords
);

std::vector<std::unordered_set<std::string>> tokenize_text_batch_core(
    const std::vector<std::string>& texts,
    const std::unordered_set<std::string>& stopwords
);
