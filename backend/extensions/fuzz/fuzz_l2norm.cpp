#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "../l2norm.cpp"
#include "fuzz_input.h"

namespace {
constexpr std::size_t kMaxFloats = 32;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 2) {
    return 0;
  }

  const std::size_t rows = xf_fuzz::bounded_size(data[0], 1, 4);
  const std::size_t cols = xf_fuzz::bounded_size(data[1], 1, 8);
  std::array<float, kMaxFloats> values{};
  for (std::size_t index = 0; index < rows * cols; ++index) {
    values[index] = xf_fuzz::signed_float(data[index % size]);
  }
  l2norm_normalize(values.data(), rows * cols);
  l2norm_normalize_batch(values.data(), rows, cols);
  return !std::isfinite(values[0]) ? 1 : 0;
}
