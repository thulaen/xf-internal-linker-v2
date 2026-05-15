#include <cstddef>
#include <cstdint>
#include <string>

#include "../counting_bloom.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 3) {
    return 0;
  }

  const std::size_t counters = xf_fuzz::bounded_size(data[0], 1, 32);
  const std::size_t hashes = xf_fuzz::bounded_size(data[1], 1, 8);
  const std::string item = xf_fuzz::slice_as_string(data, size, 2, 64);
  CountingBloomFilter filter(counters, hashes);
  filter.add(item);
  const bool was_present = filter.contains(item);
  filter.remove(item);
  return was_present ? 0 : 1;
}
