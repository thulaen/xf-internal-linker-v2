#include <benchmark/benchmark.h>

#include <cstdint>
#include <vector>

#include "bench_common.h"
#include "simsearch_core.h"

namespace {

void BM_ScoreAndTopK(benchmark::State& state) {
    const auto n_candidates = static_cast<size_t>(state.range(0));
    const size_t dim = 384;
    auto dest = xf_bench::random_floats(dim, 42);
    auto sentences = xf_bench::random_floats(n_candidates * dim, 43);
    auto rows =
        xf_bench::random_int32s(n_candidates, 0, static_cast<int32_t>(n_candidates - 1), 44);

    std::vector<int64_t> out_indices(50);
    std::vector<float> out_scores(50);
    size_t out_count = 0;

    for (auto _ : state) {
        cscore_and_topk(dest.data(), dim, sentences.data(), n_candidates, dim, rows.data(),
                        n_candidates, 50, out_indices.data(), out_scores.data(), &out_count);
        benchmark::DoNotOptimize(out_count);
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n_candidates));
}
BENCHMARK(BM_ScoreAndTopK)->Arg(100)->Arg(5000)->Arg(50000);

}  // namespace
