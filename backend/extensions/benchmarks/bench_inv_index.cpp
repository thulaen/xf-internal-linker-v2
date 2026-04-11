#include <benchmark/benchmark.h>

#include <vector>

#include "bench_common.h"
#include "inv_index_core.h"

namespace {

void BM_InvIndexBuild(benchmark::State& state) {
    const auto n_docs = static_cast<int>(state.range(0));
    const size_t tokens_per_doc = 50;
    std::vector<std::vector<uint32_t>> all_tokens;
    all_tokens.reserve(static_cast<size_t>(n_docs));
    for (int d = 0; d < n_docs; ++d) {
        all_tokens.push_back(
            xf_bench::random_uint32s(tokens_per_doc, 0, 10000, static_cast<unsigned>(42 + d)));
    }

    for (auto _ : state) {
        InvertedIndex idx;
        for (int d = 0; d < n_docs; ++d) {
            idx.add_document(d, all_tokens[static_cast<size_t>(d)]);
        }
        benchmark::DoNotOptimize(idx);
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n_docs));
}
BENCHMARK(BM_InvIndexBuild)->Arg(100)->Arg(10000)->Arg(100000);

void BM_InvIndexSearch(benchmark::State& state) {
    const auto n_docs = static_cast<int>(state.range(0));
    const size_t tokens_per_doc = 50;
    InvertedIndex idx;
    for (int d = 0; d < n_docs; ++d) {
        auto tokens =
            xf_bench::random_uint32s(tokens_per_doc, 0, 10000, static_cast<unsigned>(42 + d));
        idx.add_document(d, tokens);
    }
    auto query = xf_bench::random_uint32s(10, 0, 10000, 99);

    for (auto _ : state) {
        auto results = idx.search(query);
        benchmark::DoNotOptimize(results);
    }
    state.SetItemsProcessed(state.iterations());
}
BENCHMARK(BM_InvIndexSearch)->Arg(100)->Arg(10000)->Arg(100000);

}  // namespace
