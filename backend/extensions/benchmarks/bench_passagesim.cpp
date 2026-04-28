#include <benchmark/benchmark.h>
#include <vector>
#include <random>
#include "include/passagesim_core.h"

static void BM_PassageSim_MaxSim(benchmark::State& state) {
    size_t num_passages = (size_t)state.range(0);
    size_t dim = 1024; // BGE-M3 standard

    std::vector<float> query(dim, 0.5f);
    std::vector<float> matrix(num_passages * dim, 0.1f);
    
    // Fill with random data to avoid optimization away
    std::mt19937 gen(42);
    std::uniform_real_distribution<float> dis(-1.0f, 1.0f);
    for(auto& x : query) x = dis(gen);
    for(auto& x : matrix) x = dis(gen);

    float sim;
    size_t index;

    for (auto _ : state) {
        c_passagesim_maxsim(query.data(), matrix.data(), num_passages, dim, &sim, &index);
        benchmark::DoNotOptimize(sim);
        benchmark::DoNotOptimize(index);
    }
    
    state.SetItemsProcessed(state.iterations() * num_passages);
}

// Benchmark across common passage counts: 10, 50, 100, 200
BENCHMARK(BM_PassageSim_MaxSim)->Arg(10)->Arg(50)->Arg(100)->Arg(200);

BENCHMARK_MAIN();
