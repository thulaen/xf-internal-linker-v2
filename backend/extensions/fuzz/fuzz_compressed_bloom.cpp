#include <cstddef>
#include <cstdint>
#include <string>

#include "../compressed_bloom.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 3) {
    return 0;
  }

  const std::size_t bit_count = 8 * xf_fuzz::bounded_size(data[0], 1, 32);
  const std::size_t hashes = xf_fuzz::bounded_size(data[1], 1, 8);
  const std::string item = xf_fuzz::slice_as_string(data, size, 2, 64);
  CompressedBloomFilter filter(bit_count, hashes);
  filter.add(item);
  return filter.contains(item) ? 0 : 1;
}
