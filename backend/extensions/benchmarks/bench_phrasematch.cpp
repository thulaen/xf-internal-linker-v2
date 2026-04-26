#include <benchmark/benchmark.h>

#include "bench_common.h"
#include "phrasematch_core.h"

namespace {

void BM_LongestContiguousOverlap(benchmark::State &state) {
  const auto n = static_cast<size_t>(state.range(0));
  auto left = xf_bench::random_tokens(n, 8, 42);
  auto right = xf_bench::random_tokens(n, 8, 43);
  /* Ensure some overlap by copying a few tokens */
  for (size_t i = 0; i < std::min(n / 4, n); ++i) {
    right[i] = left[i];
  }

  for (auto _ : state) {
    int result = longest_contiguous_overlap(left, right);
    benchmark::DoNotOptimize(result);
  }
  state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n * n));
}
BENCHMARK(BM_LongestContiguousOverlap)->Arg(5)->Arg(20)->Arg(100);

} // namespace
