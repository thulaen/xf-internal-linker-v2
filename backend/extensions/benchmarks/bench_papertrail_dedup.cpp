// Benchmark for the paper-trail MinHash + LSH dedup index.
// Three input sizes per the mandatory benchmark rule (CLAUDE.md).

#include <benchmark/benchmark.h>

#include "../include/papertrail_dedup.h"

namespace {

std::string make_abstract(uint64_t i) {
  // Realistic-ish paper-trail abstract length (~50 words).
  return "Deferred paper trail entry number " + std::to_string(i) +
         " describes a multi-session refactor of subsystem X with the "
         "following blockers: dependency upgrade chain across several "
         "packages, coverage gap in two property tests, and a documentation "
         "update that needs an owner decision before the schema migration "
         "lands.";
}

}  // namespace

static void BM_AddEntry(benchmark::State& state) {
  const auto n = static_cast<size_t>(state.range(0));
  for (auto _ : state) {
    state.PauseTiming();
    xf::papertrail::DedupIndex idx(n);
    state.ResumeTiming();
    for (size_t i = 0; i < n; ++i) {
      benchmark::DoNotOptimize(idx.add_entry(i, make_abstract(i)));
    }
  }
  state.SetItemsProcessed(static_cast<int64_t>(state.iterations()) *
                          static_cast<int64_t>(n));
}
BENCHMARK(BM_AddEntry)->Arg(100)->Arg(10000)->Arg(100000);

static void BM_FindSimilar(benchmark::State& state) {
  const auto n = static_cast<size_t>(state.range(0));
  xf::papertrail::DedupIndex idx(n);
  for (size_t i = 0; i < n; ++i) idx.add_entry(i, make_abstract(i));
  const std::string query = make_abstract(n / 2);
  for (auto _ : state) {
    auto hits = idx.find_similar(query, 0.85f);
    benchmark::DoNotOptimize(hits);
  }
  state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
  state.counters["memory_mb"] =
      static_cast<double>(idx.memory_bytes()) / (1024.0 * 1024.0);
}
BENCHMARK(BM_FindSimilar)->Arg(100)->Arg(10000)->Arg(100000);

static void BM_MinhashOnly(benchmark::State& state) {
  xf::papertrail::DedupIndex idx;
  const std::string text =
      "A representative paper-trail abstract about half a paragraph long "
      "explaining why the work was deferred and what's needed to resolve it.";
  for (auto _ : state) {
    auto sig = idx.minhash(text);
    benchmark::DoNotOptimize(sig);
  }
  state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_MinhashOnly);

BENCHMARK_MAIN();
