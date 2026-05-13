// libFuzzer harness for the rare-term scoring kernel in rareterm.cpp.

#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_set>
#include <vector>

#include "include/rareterm_core.h"

namespace {
constexpr size_t kMaxTerms = 16;

std::string token_from_byte(uint8_t value) {
    return "t" + std::to_string(static_cast<unsigned int>(value));
}
}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    if (size < 2) {
        return 0;
    }

    const size_t term_count = 1 + (data[0] % kMaxTerms);
    const int max_terms = 1 + (data[1] % kMaxTerms);
    const size_t needed = 2 + term_count * 3;
    if (size < needed) {
        return 0;
    }

    std::vector<std::string> terms;
    std::vector<double> evidences;
    std::vector<int> supporting_pages;
    std::unordered_set<std::string> host_tokens;
    terms.reserve(term_count);
    evidences.reserve(term_count);
    supporting_pages.reserve(term_count);

    for (size_t index = 0; index < term_count; ++index) {
        const uint8_t term_byte = data[2 + index * 3];
        const uint8_t evidence_byte = data[3 + index * 3];
        const uint8_t page_byte = data[4 + index * 3];
        std::string term = token_from_byte(term_byte);
        terms.push_back(term);
        evidences.push_back(static_cast<double>(evidence_byte) / 255.0);
        supporting_pages.push_back(static_cast<int>(page_byte));
        if ((term_byte & 1u) == 0u) {
            host_tokens.insert(std::move(term));
        }
    }

    const auto result =
        evaluate_rare_terms_core(terms, evidences, supporting_pages, host_tokens, max_terms);
    return result.second > 10.0 ? 1 : 0;
}
