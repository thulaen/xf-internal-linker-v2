#include <benchmark/benchmark.h>

#include <vector>

#include "bench_common.h"
#include "pagerank_core.h"

namespace {

void BM_PagerankStep(benchmark::State& state) {
    const int nodes = static_cast<int>(state.range(0));
    auto graph = xf_bench::random_csr(nodes, 5, 42);
    std::vector<double> next_ranks(static_cast<size_t>(nodes));

    /* vector<bool> doesn't have .data(), so copy to a raw bool array */
    std::vector<char> dangling_raw(static_cast<size_t>(nodes));
    for (size_t i = 0; i < static_cast<size_t>(nodes); ++i) {
        dangling_raw[i] = graph.dangling[i] ? 1 : 0;
    }

    for (auto _ : state) {
        double delta = pagerank_step_core(graph.indptr.data(), graph.indices.data(),
                                          graph.data.data(), graph.ranks.data(),
                                          reinterpret_cast<const bool*>(dangling_raw.data()), 0.85,
                                          graph.node_count, next_ranks.data());
        benchmark::DoNotOptimize(delta);
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(nodes));
}
BENCHMARK(BM_PagerankStep)->Arg(100)->Arg(10000)->Arg(100000);

}  // namespace
