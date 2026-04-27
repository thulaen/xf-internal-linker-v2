// FR-045 anchor diversity C++ batch fast path — Google Benchmark.
// Three sizes per AGENTS.md §34 + BLC §1.4: 100 / 5 000 / 50 000 candidates,
// matching the feedrerank benchmark scale. The core performs constant work
// per candidate (no inner loop, no allocation), so the benchmark measures
// raw branch + divide throughput after vectorisation by -O3 -march=native.

#include <benchmark/benchmark.h>

#include <cstdint>
#include <vector>

#include "anchor_diversity_core.h"
#include "bench_common.h"

namespace {

void BM_EvaluateAnchorDiversity(benchmark::State& state) {
    const auto count = static_cast<std::size_t>(state.range(0));
    // Seeded pseudo-random so the same benchmark run is reproducible. Mix
    // of low-history, mid-history and high-concentration rows so all five
    // state branches in evaluate_anchor_diversity_core are exercised.
    auto active = xf_bench::random_int32s(count, 0, 40, 101);
    auto before = xf_bench::random_int32s(count, 0, 12, 102);
    std::vector<int32_t> out_projected_count(count);
    std::vector<double> out_projected_share(count);
    std::vector<double> out_share_overflow(count);
    std::vector<double> out_count_overflow_norm(count);
    std::vector<double> out_spam_risk(count);
    std::vector<double> out_score(count);
    std::vector<int32_t> out_state_index(count);
    std::vector<uint8_t> out_would_block(count);

    for (auto _ : state) {
        evaluate_anchor_diversity_core(
            active.data(), before.data(), count,
            /*min_history_count=*/3,
            /*max_exact_match_share=*/0.40,
            /*max_exact_match_count=*/3,
            /*hard_cap_enabled=*/false, out_projected_count.data(), out_projected_share.data(),
            out_share_overflow.data(), out_count_overflow_norm.data(), out_spam_risk.data(),
            out_score.data(), out_state_index.data(), out_would_block.data());
        benchmark::DoNotOptimize(out_score.data());
        benchmark::DoNotOptimize(out_state_index.data());
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(count));
}
BENCHMARK(BM_EvaluateAnchorDiversity)->Arg(100)->Arg(5000)->Arg(50000);

}  // namespace
