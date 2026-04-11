#include <benchmark/benchmark.h>
#include "bench_common.h"
#include "feedrerank_core.h"
#include <vector>

namespace {

void BM_RerankFactors(benchmark::State& state) {
    const auto count = static_cast<size_t>(state.range(0));
    auto successes = xf_bench::random_int32s(count, 0, 100, 42);
    auto totals = xf_bench::random_int32s(count, 1, 200, 43);
    // Map random_doubles [-1,1] → [0,1] for valid exposure probability values
    auto raw_ep = xf_bench::random_doubles(count, 44);
    std::vector<double> exposure_probs(count);
    for (std::size_t i = 0; i < count; ++i)
        exposure_probs[i] = (raw_ep[i] + 1.0) / 2.0;
    std::vector<double> out(count);

    for (auto _ : state) {
        rerank_factors_core(
            successes.data(), totals.data(),
            exposure_probs.data(),
            count,
            10000, 1.0, 1.0, 0.3, 0.1,
            out.data()
        );
        benchmark::DoNotOptimize(out.data());
    }
    state.SetItemsProcessed(
        state.iterations() * static_cast<int64_t>(count));
}
BENCHMARK(BM_RerankFactors)->Arg(100)->Arg(5000)->Arg(50000);

void BM_MmrScores(benchmark::State& state) {
    const auto n_candidates = static_cast<size_t>(state.range(0));
    const size_t n_selected = 50;
    const size_t dim = 384;
    auto relevance = xf_bench::random_doubles(n_candidates, 42);
    auto candidates = xf_bench::random_doubles(n_candidates * dim, 43);
    auto selected = xf_bench::random_doubles(n_selected * dim, 44);
    std::vector<double> out_mmr(n_candidates);
    std::vector<double> out_sim(n_candidates);

    for (auto _ : state) {
        mmr_scores_core(
            relevance.data(), n_candidates,
            candidates.data(), selected.data(),
            n_selected, dim, 0.7,
            out_mmr.data(), out_sim.data()
        );
        benchmark::DoNotOptimize(out_mmr.data());
    }
    state.SetItemsProcessed(
        state.iterations() * static_cast<int64_t>(n_candidates));
}
BENCHMARK(BM_MmrScores)->Arg(50)->Arg(500)->Arg(5000);

}  // namespace
