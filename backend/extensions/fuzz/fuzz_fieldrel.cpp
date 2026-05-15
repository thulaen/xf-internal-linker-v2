#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "../fieldrel.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 4) {
    return 0;
  }

  const std::size_t count = xf_fuzz::bounded_size(data[0], 1, 8);
  const auto tokens = xf_fuzz::byte_tokens(data, size, 1, count);
  std::vector<int> host_tfs(count);
  std::vector<int> field_tfs(count);
  std::vector<int> presence(count);
  for (std::size_t index = 0; index < count; ++index) {
    host_tfs[index] = 1 + static_cast<int>(data[(1 + index) % size] % 8);
    field_tfs[index] = static_cast<int>(data[(2 + index) % size] % 8);
    presence[index] = 1 + static_cast<int>(data[(3 + index) % size] % 8);
  }

  const double score = score_field_tokens(
      tokens, host_tfs, field_tfs, presence, 1 + static_cast<int>(data[1]),
      1.0 + static_cast<double>(data[2]), xf_fuzz::unit_double(data[3]),
      1 + static_cast<int>(count), 0.5 + xf_fuzz::unit_double(data[0]), 4);
  return score < 0.0 || score > 1.0 || !std::isfinite(score) ? 1 : 0;
}
