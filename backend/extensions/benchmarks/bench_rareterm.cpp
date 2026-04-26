#include <benchmark/benchmark.h>

#include <string>
#include <vector>

#include "bench_common.h"
#include "rareterm_core.h"

namespace {

void BM_EvaluateRareTerms(benchmark::State &state) {
  const auto n_terms = static_cast<size_t>(state.range(0));
  const auto n_host = n_terms * 5;
  auto terms = xf_bench::random_tokens(n_terms, 8, 42);
  auto evidences = xf_bench::random_doubles(n_terms, 43);
  /* Make evidences positive 0..1 */
  for (auto &e : evidences)
    e = std::abs(e);
  auto supporting = std::vector<int>(n_terms, 3);
  auto host_tokens = xf_bench::random_token_set(n_host, 8, 44);
  /* Ensure some matches by inserting some terms into host set */
  for (size_t i = 0; i < std::min(n_terms / 2, n_terms); ++i) {
    host_tokens.insert(terms[i]);
  }

  for (auto _ : state) {
    auto result =
        evaluate_rare_terms_core(terms, evidences, supporting, host_tokens, 10);
    benchmark::DoNotOptimize(result);
  }
  state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n_terms));
}
BENCHMARK(BM_EvaluateRareTerms)->Arg(10)->Arg(100)->Arg(1000);

} // namespace
