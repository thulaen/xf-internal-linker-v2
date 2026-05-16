// Benchmark for the lesson_index three-sub-index extension.
// Targets (per docs/specs/lesson-index.md):
//   - ScopedLessonIndex.add    > 100 K ops/s at 1 M entries
//   - ScopedLessonIndex.find   p99 < 5 µs at 1 M entries
//   - PerfBaselineCache.get    p99 < 1 µs at 50 K entries
//   - CitationCache.get        p99 < 2 µs at 10 K entries

#include <benchmark/benchmark.h>

#include <cstring>
#include <string>

#include "../include/lesson_index.h"

namespace li = xf::lesson_index;

namespace {
li::LessonRecord lesson(uint64_t i) {
  return li::LessonRecord{i, i * 31u, static_cast<std::uint8_t>(i % 4),
                          1'700'000'000};
}
li::BaselineRecord baseline(uint64_t i) {
  return li::BaselineRecord{i, i * 2, i * 4, i + i / 2, 1000, 1'700'000'000};
}
li::CitationRecord citation(uint64_t i) {
  li::CitationRecord c{};
  c.kind = 'd';
  auto k = "10.1/x" + std::to_string(i);
  std::strncpy(c.id.data(), k.c_str(), sizeof(c.id) - 1);
  c.year = 2024;
  c.accessible = 1;
  c.last_checked_unix = 1'700'000'000;
  return c;
}
}  // namespace

static void BM_ScopedLessonAdd(benchmark::State& state) {
  const auto n = static_cast<size_t>(state.range(0));
  for (auto _ : state) {
    state.PauseTiming();
    li::ScopedLessonIndex idx(n);
    state.ResumeTiming();
    for (size_t i = 0; i < n; ++i) {
      benchmark::DoNotOptimize(
          idx.add("backend/apps/x/y/z.py", lesson(i)));
    }
  }
  state.SetItemsProcessed(static_cast<int64_t>(state.iterations()) *
                          static_cast<int64_t>(n));
}
BENCHMARK(BM_ScopedLessonAdd)->Arg(100)->Arg(10000)->Arg(100000);

static void BM_ScopedLessonFind(benchmark::State& state) {
  const auto n = static_cast<size_t>(state.range(0));
  li::ScopedLessonIndex idx(n);
  for (size_t i = 0; i < n; ++i) idx.add("backend/apps/x/y/z.py", lesson(i));
  for (auto _ : state) {
    auto hits = idx.find_by_path("backend/apps/x/y", 5);
    benchmark::DoNotOptimize(hits);
  }
  state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
  state.counters["memory_mb"] =
      static_cast<double>(idx.memory_bytes()) / (1024.0 * 1024.0);
}
BENCHMARK(BM_ScopedLessonFind)->Arg(100)->Arg(10000)->Arg(100000);

static void BM_PerfBaselineGet(benchmark::State& state) {
  const auto n = static_cast<size_t>(state.range(0));
  li::PerfBaselineCache cache(n);
  for (size_t i = 0; i < n; ++i) {
    cache.put("fn_" + std::to_string(i), baseline(i + 1));
  }
  size_t i = 0;
  for (auto _ : state) {
    auto out = cache.get("fn_" + std::to_string(i % n));
    benchmark::DoNotOptimize(out);
    ++i;
  }
  state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_PerfBaselineGet)->Arg(100)->Arg(10000)->Arg(50000);

static void BM_CitationGet(benchmark::State& state) {
  const auto n = static_cast<size_t>(state.range(0));
  li::CitationCache cache(n);
  for (size_t i = 0; i < n; ++i) {
    cache.put("doi:" + std::to_string(i), citation(i));
  }
  size_t i = 0;
  for (auto _ : state) {
    auto out = cache.get("doi:" + std::to_string(i % n));
    benchmark::DoNotOptimize(out);
    ++i;
  }
  state.SetItemsProcessed(static_cast<int64_t>(state.iterations()));
}
BENCHMARK(BM_CitationGet)->Arg(100)->Arg(1000)->Arg(10000);

BENCHMARK_MAIN();
