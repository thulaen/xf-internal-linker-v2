#include <benchmark/benchmark.h>
#include "bench_common.h"
#include "pulse_metrics_core.h"

namespace {

void BM_PulseRingPush(benchmark::State& state) {
    PulseRing ring;
    double ts = 1000000.0;

    for (auto _ : state) {
        ring.push(ts, 1, 12.5, 100);
        ts += 60.0;
        benchmark::DoNotOptimize(ts);
    }
    state.SetItemsProcessed(state.iterations());
}
BENCHMARK(BM_PulseRingPush);

void BM_PulseRingSummary(benchmark::State& state) {
    const auto n_events = static_cast<size_t>(state.range(0));
    PulseRing ring;
    double ts = 1000000.0;
    for (size_t i = 0; i < n_events; ++i) {
        ring.push(ts, static_cast<int>(i % 4), 10.0 + static_cast<double>(i), i);
        ts += 3.6;  /* fill the hour window */
    }

    for (auto _ : state) {
        auto summary = ring.summary_raw();
        benchmark::DoNotOptimize(summary.throughput_per_min);
    }
    state.SetItemsProcessed(state.iterations());
}
BENCHMARK(BM_PulseRingSummary)->Arg(100)->Arg(500)->Arg(1000);

}  // namespace
