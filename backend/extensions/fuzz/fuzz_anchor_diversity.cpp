#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "../anchor_diversity.cpp"
#include "fuzz_input.h"

namespace {
constexpr std::size_t kMaxCount = 16;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 4) {
    return 0;
  }

  const std::size_t count = xf_fuzz::bounded_size(data[0], 1, kMaxCount);
  std::array<int32_t, kMaxCount> active{};
  std::array<int32_t, kMaxCount> before{};
  std::array<int32_t, kMaxCount> projected_count{};
  std::array<double, kMaxCount> projected_share{};
  std::array<double, kMaxCount> share_overflow{};
  std::array<double, kMaxCount> count_overflow{};
  std::array<double, kMaxCount> spam_risk{};
  std::array<double, kMaxCount> score{};
  std::array<int32_t, kMaxCount> state{};
  std::array<uint8_t, kMaxCount> would_block{};

  for (std::size_t index = 0; index < count; ++index) {
    active[index] = static_cast<int32_t>(data[(1 + index) % size] % 32);
    before[index] = static_cast<int32_t>(data[(2 + index) % size] % 32);
  }

  evaluate_anchor_diversity_core(
      active.data(), before.data(), count, static_cast<int32_t>(data[1] % 8),
      xf_fuzz::unit_double(data[2]), static_cast<int32_t>(data[3] % 32),
      (data[0] & 1U) != 0U, projected_count.data(), projected_share.data(),
      share_overflow.data(), count_overflow.data(), spam_risk.data(),
      score.data(), state.data(), would_block.data());
  return !std::isfinite(score[0]) ? 1 : 0;
}
