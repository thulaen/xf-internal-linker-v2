#include <benchmark/benchmark.h>

#include <string>
#include <vector>

#include "bench_common.h"
#include "fieldrel_core.h"

namespace {

void BM_ScoreFieldTokens(benchmark::State &state) {
  const auto n = static_cast<size_t>(state.range(0));
  auto tokens = xf_bench::random_tokens(n, 8, 42);
  auto host_tfs = std::vector<int>(n, 2);
  auto field_tfs = std::vector<int>(n, 1);
  auto field_presence = std::vector<int>(n, 50);

  for (auto _ : state) {
    double result =
        score_field_tokens(tokens, host_tfs, field_tfs, field_presence, 100,
                           80.0, 0.75, 500, 1.5, 10);
    benchmark::DoNotOptimize(result);
  }
  state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n));
}
BENCHMARK(BM_ScoreFieldTokens)->Arg(5)->Arg(20)->Arg(100);

} // namespace
