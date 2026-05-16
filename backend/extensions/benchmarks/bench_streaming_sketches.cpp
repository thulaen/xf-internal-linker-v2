#include <benchmark/benchmark.h>

#include "../compressed_bloom.cpp"
#include "../count_min_sketch.cpp"
#include "../counting_bloom.cpp"

namespace {

// Helper template — adds n synthetic items "item-0".."item-{n-1}" to a
// bloom-style filter. Extracted to remove the duplicated insert+contains
// loop that was identical between the CountingBloom and CompressedBloom
// benchmarks (quality-debt: duplicated-code, scan 2026-05-15).
template <typename Filter>
void FillBloomFilter(Filter& filter, int n) {
  for (int i = 0; i < n; ++i) {
    filter.add("item-" + std::to_string(i));
  }
}

void BM_CountingBloomAddContains(benchmark::State& state) {
  const int n = static_cast<int>(state.range(0));
  for (auto _ : state) {
    CountingBloomFilter filter(1 << 20, 4);
    FillBloomFilter(filter, n);
    benchmark::DoNotOptimize(filter.contains("item-17"));
  }
  state.SetItemsProcessed(state.iterations() * n);
}
BENCHMARK(BM_CountingBloomAddContains)->Arg(100)->Arg(10000)->Arg(100000);

void BM_CompressedBloomAddContains(benchmark::State& state) {
  const int n = static_cast<int>(state.range(0));
  for (auto _ : state) {
    CompressedBloomFilter filter(1 << 20, 4);
    FillBloomFilter(filter, n);
    benchmark::DoNotOptimize(filter.contains("item-17"));
  }
  state.SetItemsProcessed(state.iterations() * n);
}
BENCHMARK(BM_CompressedBloomAddContains)->Arg(100)->Arg(10000)->Arg(100000);

void BM_CountMinSketchAddEstimate(benchmark::State& state) {
  const int n = static_cast<int>(state.range(0));
  for (auto _ : state) {
    CountMinSketch sketch(16384, 5);
    for (int i = 0; i < n; ++i) {
      sketch.add("item-" + std::to_string(i % 1000), 1);
    }
    benchmark::DoNotOptimize(sketch.estimate("item-17"));
  }
  state.SetItemsProcessed(state.iterations() * n);
}
BENCHMARK(BM_CountMinSketchAddEstimate)->Arg(100)->Arg(10000)->Arg(100000);

}  // namespace
