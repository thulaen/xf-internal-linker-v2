#include <cmath>
#include <cstddef>
#include <cstdint>
#include <string>

#include "../api_rate_limiter.cpp"
#include "fuzz_input.h"

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
  if (size < 5) {
    return 0;
  }

  RateLimiterRegistry registry;
  const std::string name = "bucket-" + std::to_string(data[0]);
  const double capacity = 1.0 + static_cast<double>(data[1] % 16);
  const double rate = 0.1 + xf_fuzz::unit_double(data[2]);
  const std::int64_t quota = (data[3] & 1U) != 0U ? -1 : data[3] % 16;
  const double cost = 0.1 + static_cast<double>(data[4] % 8);

  registry.register_bucket(name, capacity, rate, quota);
  (void)registry.try_acquire(name, cost);
  const double wait = registry.wait_seconds(name, cost);
  const double available = registry.available(name);
  (void)registry.daily_remaining(name);
  return !std::isfinite(wait) || !std::isfinite(available) ? 1 : 0;
}
