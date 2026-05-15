#pragma once

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <string>
#include <vector>

namespace xf_fuzz {

inline std::size_t bounded_size(std::uint8_t value, std::size_t min_value,
                                std::size_t max_value) {
  if (max_value <= min_value) {
    return min_value;
  }
  return min_value +
         (static_cast<std::size_t>(value) % (max_value - min_value + 1));
}

inline std::string slice_as_string(const std::uint8_t* data, std::size_t size,
                                   std::size_t offset, std::size_t max_len) {
  if (offset >= size) {
    return {};
  }
  const std::size_t length = std::min(max_len, size - offset);
  return std::string(reinterpret_cast<const char*>(data + offset), length);
}

inline double unit_double(std::uint8_t value) {
  return static_cast<double>(value) / 255.0;
}

inline float signed_float(std::uint8_t value) {
  return (static_cast<float>(value) - 127.0F) / 32.0F;
}

inline std::vector<std::string> byte_tokens(const std::uint8_t* data,
                                            std::size_t size,
                                            std::size_t offset,
                                            std::size_t count) {
  std::vector<std::string> tokens;
  tokens.reserve(count);
  for (std::size_t index = 0; index < count; ++index) {
    const std::uint8_t value = offset + index < size ? data[offset + index] : 0;
    tokens.push_back("t" + std::to_string(static_cast<unsigned int>(value)));
  }
  return tokens;
}

}  // namespace xf_fuzz
