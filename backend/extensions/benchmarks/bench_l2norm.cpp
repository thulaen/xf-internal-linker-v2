#include <benchmark/benchmark.h>
#include "bench_common.h"
#include "l2norm_core.h"

namespace {

void BM_L2Norm1D(benchmark::State& state) {
    const auto size = static_cast<size_t>(state.range(0));
    auto data = xf_bench::random_floats(size, 42);

    for (auto _ : state) {
        auto copy = data;
        l2norm_normalize(copy.data(), copy.size());
        benchmark::DoNotOptimize(copy.data());
    }
    state.SetItemsProcessed(
        state.iterations() * static_cast<int64_t>(size));
}
BENCHMARK(BM_L2Norm1D)->Arg(128)->Arg(384)->Arg(1536);

void BM_L2NormBatch(benchmark::State& state) {
    const auto rows = static_cast<size_t>(state.range(0));
    const size_t cols = 384;
    auto data = xf_bench::random_floats(rows * cols, 42);

    for (auto _ : state) {
        auto copy = data;
        l2norm_normalize_batch(copy.data(), rows, cols);
        benchmark::DoNotOptimize(copy.data());
    }
    state.SetItemsProcessed(
        state.iterations() * static_cast<int64_t>(rows));
}
BENCHMARK(BM_L2NormBatch)->Arg(100)->Arg(10000)->Arg(100000);

}  // namespace
