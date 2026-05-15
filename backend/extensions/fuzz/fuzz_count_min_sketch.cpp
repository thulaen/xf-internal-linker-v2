#include <cstddef>
#include <cstdint>
#include <string>

#include "../count_min_sketch.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 4) {
    return 0;
  }

  const std::size_t width = xf_fuzz::bounded_size(data[0], 1, 32);
  const std::size_t depth = xf_fuzz::bounded_size(data[1], 1, 8);
  const std::uint64_t count = static_cast<std::uint64_t>(1 + (data[2] % 16));
  const std::string item = xf_fuzz::slice_as_string(data, size, 3, 64);
  CountMinSketch sketch(width, depth);
  sketch.add(item, count);
  return sketch.estimate(item) < count ? 1 : 0;
}
