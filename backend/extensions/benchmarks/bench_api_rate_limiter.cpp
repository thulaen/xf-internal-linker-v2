// FR-250 — Google Benchmark for the C++ rate limiter.
// Three input sizes per CLAUDE.md "Mandatory Benchmark Rule" section.
//
// Build: see backend/extensions/benchmarks/CMakeLists.txt; the host .cpp is
// included directly with XF_BENCH_MODE so we skip the pybind11 block.

#include <benchmark/benchmark.h>

#include <string>
#include <vector>

#include "../api_rate_limiter.cpp"  // brings in RateLimiterRegistry

namespace {

// Preload buckets so the hot-path benchmarks do not measure registration work.
void populate_registry(RateLimiterRegistry& reg, int n_buckets) {
    for (int i = 0; i < n_buckets; ++i) {
        reg.register_bucket("bucket-" + std::to_string(i),
                            /*capacity=*/1000.0,
                            /*rate_per_sec=*/1000.0,
                            /*daily_quota=*/-1);
    }
}

void BM_TryAcquireHotPath(benchmark::State& state) {
    const int n = static_cast<int>(state.range(0));
    RateLimiterRegistry reg;
    populate_registry(reg, n);
    int idx = 0;
    for (auto _ : state) {
        const std::string name = "bucket-" + std::to_string(idx % n);
        bool ok = reg.try_acquire(name, 1.0);
        benchmark::DoNotOptimize(ok);
        ++idx;
    }
    state.SetItemsProcessed(state.iterations());
}
BENCHMARK(BM_TryAcquireHotPath)->Arg(1)->Arg(100)->Arg(10000);

void BM_WaitSecondsHotPath(benchmark::State& state) {
    const int n = static_cast<int>(state.range(0));
    RateLimiterRegistry reg;
    populate_registry(reg, n);
    int idx = 0;
    for (auto _ : state) {
        const std::string name = "bucket-" + std::to_string(idx % n);
        double w = reg.wait_seconds(name, 1.0);
        benchmark::DoNotOptimize(w);
        ++idx;
    }
    state.SetItemsProcessed(state.iterations());
}
BENCHMARK(BM_WaitSecondsHotPath)->Arg(1)->Arg(100)->Arg(10000);

void BM_RegisterBucket(benchmark::State& state) {
    const int n = static_cast<int>(state.range(0));
    for (auto _ : state) {
        RateLimiterRegistry reg;
        for (int i = 0; i < n; ++i) {
            reg.register_bucket("b-" + std::to_string(i), 100.0, 50.0, -1);
        }
        benchmark::DoNotOptimize(reg);
    }
    state.SetItemsProcessed(state.iterations() * n);
}
BENCHMARK(BM_RegisterBucket)->Arg(1)->Arg(100)->Arg(10000);

}  // namespace
