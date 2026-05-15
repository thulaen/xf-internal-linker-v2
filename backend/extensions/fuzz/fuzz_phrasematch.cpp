#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "../phrasematch.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 2) {
    return 0;
  }

  const std::size_t left_count = xf_fuzz::bounded_size(data[0], 1, 8);
  const std::size_t right_count = xf_fuzz::bounded_size(data[1], 1, 8);
  const auto left = xf_fuzz::byte_tokens(data, size, 2, left_count);
  const auto right =
      xf_fuzz::byte_tokens(data, size, 2 + left_count, right_count);
  const int overlap = longest_contiguous_overlap(left, right);
  return overlap < 0 || static_cast<std::size_t>(overlap) > left.size() ? 1 : 0;
}
