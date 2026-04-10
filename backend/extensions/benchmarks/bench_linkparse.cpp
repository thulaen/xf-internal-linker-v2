#include <benchmark/benchmark.h>
#include "bench_common.h"
#include "linkparse_core.h"

namespace {

void BM_FindUrls(benchmark::State& state) {
    const auto approx_len = static_cast<size_t>(state.range(0));
    auto bbcode = xf_bench::random_bbcode(approx_len, 42);

    for (auto _ : state) {
        auto results = find_urls(bbcode);
        benchmark::DoNotOptimize(results);
    }
    state.SetItemsProcessed(state.iterations());
    state.SetBytesProcessed(
        state.iterations() * static_cast<int64_t>(bbcode.size()));
}
BENCHMARK(BM_FindUrls)->Arg(500)->Arg(10000)->Arg(100000);

}  // namespace
