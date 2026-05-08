#include <benchmark/benchmark.h>

#include <random>
#include <vector>

#include "include/quantemb_core.h"

static void BM_QuantEmb_OPQ_Encode(benchmark::State& state) {
    size_t num_vectors = (size_t)state.range(0);
    size_t dim = 1024;
    size_t m = 32;
    size_t k = 256;
    size_t sub_dim = dim / m;

    std::vector<float> vectors(num_vectors * dim);
    std::vector<float> rotation(dim * dim);
    std::vector<float> codebooks(m * k * sub_dim);
    std::vector<uint8_t> out_codes(num_vectors * m);

    std::mt19937 gen(42);
    std::uniform_real_distribution<float> dis(-1.0f, 1.0f);
    for (auto& x : vectors)
        x = dis(gen);
    for (auto& x : rotation)
        x = dis(gen);
    for (auto& x : codebooks)
        x = dis(gen);

    for (auto _ : state) {
        c_opq_encode(vectors.data(), num_vectors, dim, rotation.data(), codebooks.data(), m, k,
                     out_codes.data());
        benchmark::DoNotOptimize(out_codes);
    }

    state.SetItemsProcessed(state.iterations() * num_vectors);
}

// Benchmark across common batch sizes: 1, 8, 32, 64
BENCHMARK(BM_QuantEmb_OPQ_Encode)->Arg(1)->Arg(8)->Arg(32)->Arg(64);

BENCHMARK_MAIN();
