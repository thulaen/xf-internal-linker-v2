#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "../feedrerank.cpp"
#include "fuzz_input.h"

namespace {
constexpr std::size_t kMaxCount = 8;
constexpr std::size_t kMaxSelected = 4;
constexpr std::size_t kMaxWidth = 4;
}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 5) {
    return 0;
  }

  const std::size_t count = xf_fuzz::bounded_size(data[0], 1, kMaxCount);
  std::array<int32_t, kMaxCount> successes{};
  std::array<int32_t, kMaxCount> totals{};
  std::array<double, kMaxCount> confidence{};
  std::array<double, kMaxCount> factors{};
  for (std::size_t index = 0; index < count; ++index) {
    successes[index] = static_cast<int32_t>(data[(1 + index) % size] % 8);
    totals[index] =
        successes[index] + static_cast<int32_t>(data[(2 + index) % size] % 8);
    confidence[index] = xf_fuzz::unit_double(data[(3 + index) % size]);
  }

  rerank_factors_core(successes.data(), totals.data(), confidence.data(), count,
                      static_cast<int>(count + data[1]), 1.0, 1.0,
                      xf_fuzz::unit_double(data[2]),
                      xf_fuzz::unit_double(data[3]), factors.data());
  const std::size_t selected = xf_fuzz::bounded_size(data[4], 1, kMaxSelected);
  const std::size_t width = xf_fuzz::bounded_size(data[0], 1, kMaxWidth);
  std::array<double, kMaxCount * kMaxWidth> candidates{};
  std::array<double, kMaxSelected * kMaxWidth> selected_rows{};
  std::array<double, kMaxCount> relevance{};
  std::array<double, kMaxCount> mmr{};
  std::array<double, kMaxCount> max_sim{};
  for (std::size_t index = 0; index < candidates.size(); ++index) {
    candidates[index] = xf_fuzz::unit_double(data[index % size]);
  }
  for (std::size_t index = 0; index < selected_rows.size(); ++index) {
    selected_rows[index] = xf_fuzz::unit_double(data[(index + 1) % size]);
  }
  for (std::size_t index = 0; index < count; ++index) {
    relevance[index] = xf_fuzz::unit_double(data[(index + 2) % size]);
  }
  mmr_scores_core(relevance.data(), count, candidates.data(),
                  selected_rows.data(), selected, width,
                  xf_fuzz::unit_double(data[3]), mmr.data(), max_sim.data());
  return !std::isfinite(factors[0]) || !std::isfinite(mmr[0]) ? 1 : 0;
}
