#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "../pagerank.cpp"
#include "fuzz_input.h"

namespace {
constexpr int kMaxNodes = 6;
}

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 2) {
    return 0;
  }

  const int node_count =
      static_cast<int>(xf_fuzz::bounded_size(data[0], 1, kMaxNodes));
  std::array<int32_t, kMaxNodes + 1> indptr{};
  std::array<int32_t, kMaxNodes> indices{};
  std::array<double, kMaxNodes> weights{};
  std::array<double, kMaxNodes> ranks{};
  std::array<double, kMaxNodes> personalization{};
  std::array<bool, kMaxNodes> dangling{};
  std::array<double, kMaxNodes> next{};
  std::array<double, kMaxNodes> next_authority{};
  std::array<double, kMaxNodes> next_hub{};

  for (int index = 0; index < node_count; ++index) {
    indptr[static_cast<std::size_t>(index)] = index;
    indices[static_cast<std::size_t>(index)] = index;
    weights[static_cast<std::size_t>(index)] =
        1.0 + xf_fuzz::unit_double(data[index % size]);
    ranks[static_cast<std::size_t>(index)] =
        1.0 / static_cast<double>(node_count);
    personalization[static_cast<std::size_t>(index)] =
        ranks[static_cast<std::size_t>(index)];
    dangling[static_cast<std::size_t>(index)] = (data[index % size] & 1U) != 0U;
  }
  indptr[static_cast<std::size_t>(node_count)] = node_count;

  const double damping = xf_fuzz::unit_double(data[1]);
  const double delta = pagerank_step_core(
      indptr.data(), indices.data(), weights.data(), ranks.data(),
      dangling.data(), damping, node_count, next.data());
  const double seeded_delta = personalized_pagerank_step_core(
      indptr.data(), indices.data(), weights.data(), ranks.data(),
      dangling.data(), personalization.data(), damping, node_count,
      next.data());
  hits_step_core(indptr.data(), indices.data(), weights.data(), ranks.data(),
                 ranks.data(), node_count, next_authority.data(),
                 next_hub.data());
  return !std::isfinite(delta) || !std::isfinite(seeded_delta) ? 1 : 0;
}
