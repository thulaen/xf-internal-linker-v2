#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <string>
#include <vector>

namespace py = pybind11;

int longest_contiguous_overlap(
    const std::vector<std::string>& left,
    const std::vector<std::string>& right
) {
    int best = 0;
    for (size_t left_start = 0; left_start < left.size(); ++left_start) {
        for (size_t right_start = 0; right_start < right.size(); ++right_start) {
            int match_len = 0;
            while (
                left_start + static_cast<size_t>(match_len) < left.size() &&
                right_start + static_cast<size_t>(match_len) < right.size() &&
                left[left_start + static_cast<size_t>(match_len)] ==
                    right[right_start + static_cast<size_t>(match_len)]
            ) {
                ++match_len;
            }
            if (match_len > best) {
                best = match_len;
            }
        }
    }
    return best;
}

PYBIND11_MODULE(phrasematch, m) {
    m.def(
        "longest_contiguous_overlap",
        &longest_contiguous_overlap,
        "Find the longest contiguous overlap length between two token lists"
    );
}
