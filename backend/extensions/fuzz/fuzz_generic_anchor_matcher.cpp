#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

#include "../generic_anchor_matcher.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 2) {
    return 0;
  }

  const std::size_t phrase_count = xf_fuzz::bounded_size(data[0], 1, 6);
  std::vector<std::string> phrases;
  phrases.reserve(phrase_count);
  for (std::size_t index = 0; index < phrase_count; ++index) {
    phrases.push_back("p" + std::to_string(static_cast<unsigned int>(
                                data[(1 + index) % size])));
  }

  const auto automaton = build_automaton(phrases);
  const std::string text = xf_fuzz::slice_as_string(data, size, 1, 128);
  const auto matches = find_all(automaton, text);
  return matches.size() > phrases.size() ? 1 : 0;
}
