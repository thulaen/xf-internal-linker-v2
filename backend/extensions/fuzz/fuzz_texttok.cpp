// libFuzzer harness for the ASCII tokenization kernel in texttok.cpp.

#include <cstddef>
#include <cstdint>
#include <string>
#include <unordered_set>

#include "include/texttok_core.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size == 0) {
    return 0;
  }

  const std::string text(reinterpret_cast<const char*>(data), size);
  const std::unordered_set<std::string> stopwords = {"a", "the", "and"};
  const auto tokens = tokenize_one_core(text, stopwords);
  return tokens.size() > size ? 1 : 0;
}
