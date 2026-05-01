#include <benchmark/benchmark.h>
#include <vector>
#include <random>
#include <cstdint>
#include "include/ivf_index_core.h"

namespace {

constexpr size_t kDim = 1024;       // BGE-M3 standard
constexpr size_t kSubquantisers = 8;  // M
constexpr size_t kCentroidsPerSubq = 256;  // K

}  // namespace

// 1. Centroid-search benchmark — N centroid count varies.
static void BM_IvfFindTopCentroids(benchmark::State& state) {
    const size_t n_centroids = static_cast<size_t>(state.range(0));
    const size_t nprobe = 16;

    std::mt19937 gen(42);
    std::uniform_real_distribution<float> dis(-1.0f, 1.0f);

    std::vector<float> query(kDim);
    std::vector<float> centroids(n_centroids * kDim);
    for (auto& x : query) x = dis(gen);
    for (auto& x : centroids) x = dis(gen);

    std::vector<int32_t> out_ids(nprobe);
    std::vector<float> out_dists(nprobe);

    for (auto _ : state) {
        c_ivf_find_top_centroids(
            query.data(), centroids.data(),
            n_centroids, kDim, nprobe,
            out_ids.data(), out_dists.data());
        benchmark::DoNotOptimize(out_ids.data());
        benchmark::DoNotOptimize(out_dists.data());
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n_centroids));
}
BENCHMARK(BM_IvfFindTopCentroids)->Arg(1024)->Arg(4096)->Arg(16384);

// 2. ADC LUT build — fixed at production geometry.
static void BM_IvfBuildAdcLut(benchmark::State& state) {
    std::mt19937 gen(42);
    std::uniform_real_distribution<float> dis(-1.0f, 1.0f);

    std::vector<float> query(kDim);
    std::vector<float> rotation(kDim * kDim);
    std::vector<float> codebooks(kSubquantisers * kCentroidsPerSubq * (kDim / kSubquantisers));
    for (auto& x : query) x = dis(gen);
    for (auto& x : rotation) x = dis(gen);
    for (auto& x : codebooks) x = dis(gen);

    std::vector<float> lut(kSubquantisers * kCentroidsPerSubq);

    for (auto _ : state) {
        c_ivf_build_adc_lut(
            query.data(), rotation.data(), codebooks.data(),
            kDim, kSubquantisers, kCentroidsPerSubq,
            lut.data());
        benchmark::DoNotOptimize(lut.data());
    }
}
BENCHMARK(BM_IvfBuildAdcLut);

// 3. ADC scoring — vary the per-partition population that gets scored.
static void BM_IvfAdcDistanceLoop(benchmark::State& state) {
    const size_t pop = static_cast<size_t>(state.range(0));

    std::mt19937 gen(42);
    std::uniform_real_distribution<float> dis(0.1f, 5.0f);
    std::uniform_int_distribution<int> code_dis(0, static_cast<int>(kCentroidsPerSubq) - 1);

    std::vector<float> lut(kSubquantisers * kCentroidsPerSubq);
    for (auto& x : lut) x = dis(gen);

    std::vector<uint8_t> codes(pop * kSubquantisers);
    for (auto& x : codes) x = static_cast<uint8_t>(code_dis(gen));

    for (auto _ : state) {
        float total = 0.0f;
        for (size_t i = 0; i < pop; ++i) {
            total += c_ivf_adc_distance(
                &codes[i * kSubquantisers], lut.data(),
                kSubquantisers, kCentroidsPerSubq);
        }
        benchmark::DoNotOptimize(total);
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(pop));
}
BENCHMARK(BM_IvfAdcDistanceLoop)->Arg(100)->Arg(1000)->Arg(10000);

BENCHMARK_MAIN();
