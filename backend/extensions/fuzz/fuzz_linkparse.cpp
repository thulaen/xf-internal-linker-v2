#include <cstddef>
#include <cstdint>
#include <string>

#include "../linkparse.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  std::string text = xf_fuzz::slice_as_string(data, size, 0, 128);
  if (size > 0 && (data[0] & 1U) != 0U) {
    text = "[url=https://example.test]" + text + "[/url]";
  }
  if (size > 1 && (data[1] & 1U) != 0U) {
    text += "<a href=\"https://example.test/path\">anchor</a>";
  }
  const auto matches = find_urls(text);
  return matches.size() > text.size() ? 1 : 0;
}
