#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>

#include "../anchor_descriptiveness.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 2) {
    return 0;
  }

  const std::size_t split = 1 + (data[0] % (size - 1));
  const std::string left = xf_fuzz::slice_as_string(data, split, 1, 64);
  const std::string right = xf_fuzz::slice_as_string(data, size, split, 64);
  const auto distance = damerau_levenshtein(left, right);
  const double jaccard = char_trigram_jaccard(left, right);
  return distance > left.size() + right.size() || !std::isfinite(jaccard) ? 1
                                                                          : 0;
}
