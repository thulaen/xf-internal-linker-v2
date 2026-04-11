#include <benchmark/benchmark.h>

#include "bench_common.h"
#include "strpool_core.h"

namespace {

void BM_StringPoolIntern(benchmark::State& state) {
    const auto n = static_cast<size_t>(state.range(0));
    auto tokens = xf_bench::random_tokens(n, 12, 42);

    for (auto _ : state) {
        StringPool pool;
        for (const auto& t : tokens) {
            auto id = pool.intern(t);
            benchmark::DoNotOptimize(id);
        }
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n));
}
BENCHMARK(BM_StringPoolIntern)->Arg(1000)->Arg(100000)->Arg(1000000);

void BM_StringPoolLookup(benchmark::State& state) {
    const auto n = static_cast<size_t>(state.range(0));
    auto tokens = xf_bench::random_tokens(n, 12, 42);
    StringPool pool;
    for (const auto& t : tokens) {
        pool.intern(t);
    }

    for (auto _ : state) {
        for (uint32_t i = 0; i < static_cast<uint32_t>(pool.size()); ++i) {
            auto s = pool.get(i);
            benchmark::DoNotOptimize(s);
        }
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(pool.size()));
}
BENCHMARK(BM_StringPoolLookup)->Arg(1000)->Arg(100000)->Arg(1000000);

}  // namespace
