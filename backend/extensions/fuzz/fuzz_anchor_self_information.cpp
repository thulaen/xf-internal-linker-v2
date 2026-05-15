#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>

#include "../anchor_self_information.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  const std::string text = xf_fuzz::slice_as_string(data, size, 0, 128);
  const double entropy = bigram_entropy(text);
  return entropy < 0.0 || !std::isfinite(entropy) ? 1 : 0;
}
