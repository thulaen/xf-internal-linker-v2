// anchor_descriptiveness.cpp — pick #anti-garbage Algo 2
//
// References
// ----------
// Damerau, F. J. (1964). "A technique for computer detection and
// correction of spelling errors." Communications of the ACM, 7(3),
// 171-176. — basis for the edit-distance variant that includes
// adjacent transpositions.
//
// Broder, A. Z. (1997). "On the Resemblance and Containment of
// Documents." Compression and Complexity of Sequences. — Jaccard
// over character n-grams as the resemblance measure.
//
// What this kernel does
// ---------------------
// Two functions exposed to Python:
//
//   damerau_levenshtein(a, b)       → int
//       Optimal-substructure DP with adjacent-transposition
//       extension. O(n × m) time, O(min(n, m)) memory via the
//       rolling-row trick.
//
//   char_trigram_jaccard(a, b)      → double
//       |trigrams(a) ∩ trigrams(b)| / |trigrams(a) ∪ trigrams(b)|.
//       Linear time + linear memory via two ``unordered_set``
//       passes.
//
// PARITY: both functions match the pure-Python implementations in
// ``apps/pipeline/services/anchor_garbage_signals.py`` byte-for-byte
// (except for the obvious type / overflow guards C++ requires).
//
// Cold-start behaviour
// --------------------
// - Either string empty → distance is the other's length, jaccard
//   is 0.0. Same as Python.
// - Two strings shorter than the n-gram length → fall back to
//   single-string-as-only-gram set semantics (same as Python).

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <string_view>
#include <unordered_set>
#include <vector>

namespace py = pybind11;

namespace {

constexpr std::size_t CHAR_NGRAM = 3;

// PARITY: matches anchor_garbage_signals.py::_damerau_levenshtein.
//
// Three rolling rows track the recurrence; ``prev_prev_row`` is the
// two-rows-ago state needed for the Damerau transposition extension
// (Damerau 1964 §3). Memory is O(min(n, m)) because we always swap
// the shorter input into ``b``.
std::size_t damerau_levenshtein_core(std::string_view a, std::string_view b) {
    if (a.empty()) {
        return b.size();
    }
    if (b.empty()) {
        return a.size();
    }
    if (a.size() < b.size()) {
        std::swap(a, b);
    }
    const std::size_t n = a.size();
    const std::size_t m = b.size();
    std::vector<std::size_t> prev_prev_row(m + 1, 0);
    std::vector<std::size_t> prev_row(m + 1, 0);
    std::vector<std::size_t> curr_row(m + 1, 0);
    for (std::size_t j = 0; j <= m; ++j) {
        prev_row[j] = j;
    }
    for (std::size_t i = 1; i <= n; ++i) {
        curr_row[0] = i;
        for (std::size_t j = 1; j <= m; ++j) {
            const std::size_t cost = (a[i - 1] == b[j - 1]) ? 0 : 1;
            const std::size_t insertion = curr_row[j - 1] + 1;
            const std::size_t deletion = prev_row[j] + 1;
            const std::size_t substitution = prev_row[j - 1] + cost;
            curr_row[j] = std::min({insertion, deletion, substitution});
            // Damerau transposition — only applicable when the
            // adjacent characters in both strings swap exactly.
            if (i > 1 && j > 1
                && a[i - 1] == b[j - 2]
                && a[i - 2] == b[j - 1]) {
                curr_row[j] = std::min(curr_row[j], prev_prev_row[j - 2] + cost);
            }
        }
        // Rotate rows: prev_prev ← prev, prev ← curr, curr ← prev_prev (reuse buffer).
        std::swap(prev_prev_row, prev_row);
        std::swap(prev_row, curr_row);
    }
    return prev_row[m];
}

// Whitespace-collapse: replace any run of whitespace bytes with a
// single space. Matches the Python ``re.sub(r"\s+", " ", text)`` so
// the n-gram sets compare apples-to-apples.
std::string collapse_whitespace(std::string_view text) {
    std::string out;
    out.reserve(text.size());
    bool last_space = false;
    for (char c : text) {
        const bool is_space = (c == ' ' || c == '\t' || c == '\n'
                               || c == '\r' || c == '\v' || c == '\f');
        if (is_space) {
            if (!last_space) {
                out.push_back(' ');
                last_space = true;
            }
        } else {
            out.push_back(c);
            last_space = false;
        }
    }
    return out;
}

// PARITY: matches anchor_garbage_signals.py::_char_ngrams.
std::unordered_set<std::string> char_ngrams(std::string_view text, std::size_t n) {
    std::unordered_set<std::string> out;
    const std::string norm = collapse_whitespace(text);
    if (norm.size() < n) {
        if (!norm.empty()) {
            out.emplace(norm);
        }
        return out;
    }
    for (std::size_t i = 0; i + n <= norm.size(); ++i) {
        out.emplace(norm.substr(i, n));
    }
    return out;
}

}  // namespace

std::size_t damerau_levenshtein(const std::string& a, const std::string& b) {
    return damerau_levenshtein_core(a, b);
}

double char_trigram_jaccard(const std::string& a, const std::string& b) {
    const auto grams_a = char_ngrams(a, CHAR_NGRAM);
    const auto grams_b = char_ngrams(b, CHAR_NGRAM);
    if (grams_a.empty() || grams_b.empty()) {
        return 0.0;
    }
    std::size_t inter = 0;
    // Iterate the smaller set for the intersection.
    const auto& smaller = (grams_a.size() <= grams_b.size()) ? grams_a : grams_b;
    const auto& larger = (grams_a.size() <= grams_b.size()) ? grams_b : grams_a;
    for (const auto& g : smaller) {
        if (larger.count(g) > 0) {
            ++inter;
        }
    }
    const std::size_t uni = grams_a.size() + grams_b.size() - inter;
    if (uni == 0) {
        return 0.0;
    }
    return static_cast<double>(inter) / static_cast<double>(uni);
}

PYBIND11_MODULE(anchor_descriptiveness, m) {
    m.doc() = "Anchor-text descriptiveness — Damerau-Levenshtein + "
              "char-trigram Jaccard.";
    m.def(
        "damerau_levenshtein",
        &damerau_levenshtein,
        py::arg("a"),
        py::arg("b"),
        "Damerau-Levenshtein edit distance with adjacent-transposition."
    );
    m.def(
        "char_trigram_jaccard",
        &char_trigram_jaccard,
        py::arg("a"),
        py::arg("b"),
        "Jaccard similarity over character 3-grams of the two inputs."
    );
}
