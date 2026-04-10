#include <benchmark/benchmark.h>
#include "bench_common.h"
#include "scoring_core.h"
#include <vector>

namespace {

void BM_ScoreFullBatch(benchmark::State& state) {
    const auto n_rows = static_cast<size_t>(state.range(0));
    const size_t n_components = 8;
    auto components = xf_bench::random_floats(n_rows * n_components, 42);
    auto weights = xf_bench::random_floats(n_components, 43);
    auto silos = xf_bench::random_floats(n_rows, 44);
    std::vector<float> out(n_rows);

    for (auto _ : state) {
        cscore_full_batch(
            components.data(), n_rows, n_components,
            weights.data(), n_components,
            silos.data(), n_rows,
            out.data()
        );
        benchmark::DoNotOptimize(out.data());
    }
    state.SetItemsProcessed(
        state.iterations() * static_cast<int64_t>(n_rows));
}
BENCHMARK(BM_ScoreFullBatch)->Arg(100)->Arg(10000)->Arg(100000);

}  // namespace
