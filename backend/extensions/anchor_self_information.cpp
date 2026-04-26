// anchor_self_information.cpp — pick #anti-garbage Algo 3
//
// Reference
// ---------
// Shannon, C. E. (1948). "A Mathematical Theory of Communication."
// Bell System Technical Journal, 27(3+4). Section 9 ("Entropy of an
// Information Source") — formal basis for the bigram-entropy
// computation here.
//
// What this kernel does
// ---------------------
// Computes character-level bigram entropy of an input string in
// O(n) time + O(unique_bigrams) memory. Mirrors the pure-Python
// implementation in
// ``apps/pipeline/services/anchor_garbage_signals.py::_bigram_entropy``
// byte-for-byte (within float-rounding tolerance) so the Python
// fallback and the C++ kernel produce identical results — the only
// difference is throughput.
//
// Cold-start behaviour
// --------------------
// - len(text) < 2 → returns 0.0 (no bigrams to count).
// - Empty / null bigram counter → returns 0.0.
// - All other inputs return H(X) = -Σ p(x) log₂ p(x) in bits.
//
// Per CPP-RULES §1, this file is built with -std=c++17 -O3
// -march=native -Wall -Wextra -Wpedantic -Werror -Wconversion
// -fno-exceptions -fno-rtti.

#include <pybind11/pybind11.h>
#include <pybind11/stl.h>

#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_map>

namespace py = pybind11;

// PARITY: matches anchor_garbage_signals.py::_bigram_entropy.
//
// Bigram counter is a flat ``unordered_map`` rather than a fixed
// 256×256 array because input strings can contain multi-byte UTF-8
// sequences — collapsing UTF-8 byte pairs into a 16-bit key would
// over-count for non-ASCII text. The map's amortised insert is O(1).
double bigram_entropy_core(const std::string &text) {
  const std::size_t n = text.size();
  if (n < 2) {
    return 0.0;
  }
  std::unordered_map<std::uint16_t, std::uint32_t> counts;
  counts.reserve(n); // upper-bound; saves rehashes.
  std::uint32_t total = 0;
  for (std::size_t i = 0; i + 1 < n; ++i) {
    // Pack the two-byte bigram into a uint16 key. Using
    // unsigned char widening to avoid sign-extension surprises
    // on platforms where ``char`` is signed.
    const auto a = static_cast<std::uint8_t>(text[i]);
    const auto b = static_cast<std::uint8_t>(text[i + 1]);
    const std::uint16_t key =
        static_cast<std::uint16_t>((static_cast<std::uint16_t>(a) << 8) | b);
    ++counts[key];
    ++total;
  }
  if (total == 0) {
    return 0.0;
  }
  const double inv_total = 1.0 / static_cast<double>(total);
  double h = 0.0;
  for (const auto &[_, c] : counts) {
    // PARITY: identical math to the Python loop.
    const double p = static_cast<double>(c) * inv_total;
    // log2(p) is well-defined because p > 0 (we only iterate
    // entries that were incremented at least once).
    h -= p * std::log2(p);
  }
  return h;
}

double bigram_entropy(const std::string &text) {
  return bigram_entropy_core(text);
}

PYBIND11_MODULE(anchor_self_information, m) {
  m.doc() = "Shannon character-bigram entropy for anchor self-information.";
  m.def("bigram_entropy", &bigram_entropy, py::arg("text"),
        "Return Shannon character-bigram entropy of *text* in bits.");
}
