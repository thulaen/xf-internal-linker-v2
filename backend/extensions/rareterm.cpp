#ifndef XF_BENCH_MODE
#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
namespace py = pybind11;
#endif
#include <algorithm>
#include <stdexcept>
#include <string>
#include <unordered_set>
#include <utility>
#include <vector>

#include "include/rareterm_core.h"

std::pair<bool, double> evaluate_rare_terms_core(
    const std::vector<std::string>& terms, const std::vector<double>& term_evidences,
    const std::vector<int>& supporting_pages, const std::unordered_set<std::string>& host_token_set,
    int max_terms) {
    const size_t term_count = terms.size();
    if (term_evidences.size() != term_count || supporting_pages.size() != term_count) {
        throw std::runtime_error(
            "terms, term_evidences, and supporting_pages must "
            "be positionally aligned");
    }

    struct MatchedTerm {
        std::string term;
        double evidence;
        int supporting_page_count;
    };

    std::vector<MatchedTerm> matched_terms;
    for (size_t index = 0; index < term_count; ++index) {
        if (host_token_set.find(terms[index]) == host_token_set.end()) {
            continue;
        }
        matched_terms.push_back({terms[index], term_evidences[index], supporting_pages[index]});
    }

    if (matched_terms.empty()) {
        return {false, 0.0};
    }

    std::sort(matched_terms.begin(), matched_terms.end(),
              [](const MatchedTerm& left, const MatchedTerm& right) {
                  if (left.evidence != right.evidence) {
                      return left.evidence > right.evidence;
                  }
                  if (left.supporting_page_count != right.supporting_page_count) {
                      return left.supporting_page_count > right.supporting_page_count;
                  }
                  return left.term < right.term;
              });

    const size_t keep_count = std::min(static_cast<size_t>(max_terms), matched_terms.size());
    double rare_term_lift = 0.0;
    for (size_t index = 0; index < keep_count; ++index) {
        rare_term_lift += matched_terms[index].evidence;
    }
    rare_term_lift /= static_cast<double>(keep_count);
    return {true, 0.5 + 0.5 * rare_term_lift};
}

#ifndef XF_BENCH_MODE
std::pair<bool, double> evaluate_rare_terms(const std::vector<std::string>& terms,
                                            const std::vector<double>& term_evidences,
                                            const std::vector<int>& supporting_pages,
                                            const py::iterable& host_tokens, int max_terms) {
    std::unordered_set<std::string> host_token_set;
    host_token_set.reserve(py::len(host_tokens));
    for (const auto& item : host_tokens) {
        host_token_set.insert(py::cast<std::string>(item));
    }
    return evaluate_rare_terms_core(terms, term_evidences, supporting_pages, host_token_set,
                                    max_terms);
}

PYBIND11_MODULE(rareterm, m) {
    m.def("evaluate_rare_terms", &evaluate_rare_terms,
          "Score aligned rare terms where index i refers to the same term, "
          "evidence, and "
          "supporting page count");
}
#endif
