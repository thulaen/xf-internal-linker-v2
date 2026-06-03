#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>

#include "../include/papertrail_dedup.h"

namespace {

std::string fuzz_text(const uint8_t* data, size_t size, size_t offset) {
  if (offset >= size) {
    return {};
  }
  const size_t length = std::min<size_t>(size - offset, 128);
  return std::string(reinterpret_cast<const char*>(data + offset), length);
}

}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (data == nullptr || size < 3) {
    return 0;
  }

  const std::size_t capacity = static_cast<std::size_t>(data[0] % 8U) + 1U;
  xf::papertrail::DedupIndex index(capacity,
                                   static_cast<std::uint64_t>(data[1]));
  const std::string first = fuzz_text(data, size, 2);
  const std::string second = fuzz_text(data, size, 3);
  const std::uint64_t entry_id = static_cast<std::uint64_t>(data[2]) + 1U;

  (void)index.minhash(first);
  (void)index.add_entry(entry_id, first);
  (void)index.has_duplicate(second, 0.5f);
  (void)index.find_similar(second, 0.5f);
  (void)index.remove_entry(entry_id);
  return 0;
}
