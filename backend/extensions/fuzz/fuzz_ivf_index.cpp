#include <array>
#include <cmath>
#include <cstddef>
#include <cstdint>

#include "../ivf_index.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 4) {
    return 0;
  }

  constexpr std::size_t dim = 4;
  constexpr std::size_t centroids = 4;
  constexpr std::size_t nprobe = 2;
  constexpr std::size_t m = 2;
  constexpr std::size_t k = 4;
  std::array<float, dim> query{};
  std::array<float, centroids * dim> centroid_values{};
  std::array<int32_t, nprobe> centroid_ids{};
  std::array<float, nprobe> centroid_dists{};
  for (std::size_t index = 0; index < centroid_values.size(); ++index) {
    centroid_values[index] = xf_fuzz::signed_float(data[index % size]);
  }
  for (std::size_t index = 0; index < query.size(); ++index) {
    query[index] = xf_fuzz::signed_float(data[(index + 1) % size]);
  }

  c_ivf_find_top_centroids(query.data(), centroid_values.data(), centroids, dim,
                           nprobe, centroid_ids.data(), centroid_dists.data());
  std::array<float, dim * dim> rotation{};
  std::array<float, m * k*(dim / m)> codebooks{};
  std::array<float, m * k> lut{};
  for (std::size_t index = 0; index < dim; ++index) {
    rotation[index * dim + index] = 1.0F;
  }
  for (std::size_t index = 0; index < codebooks.size(); ++index) {
    codebooks[index] = xf_fuzz::signed_float(data[(index + 2) % size]);
  }
  c_ivf_build_adc_lut(query.data(), rotation.data(), codebooks.data(), dim, m,
                      k, lut.data());
  std::array<uint8_t, m> code{static_cast<uint8_t>(data[0] % k),
                              static_cast<uint8_t>(data[1] % k)};
  const float distance = c_ivf_adc_distance(code.data(), lut.data(), m, k);
  return !std::isfinite(distance) ? 1 : 0;
}
