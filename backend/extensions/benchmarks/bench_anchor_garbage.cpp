// Phase 0.10 — Mandatory Benchmark Rule coverage for the three
// anti-garbage anchor algorithms (PR-Anchor; commit b08daba):
//   * generic_anchor_matcher  — Aho-Corasick blacklist matcher
//   * anchor_descriptiveness  — Damerau-Levenshtein + char-trigram Jaccard
//   * anchor_self_information — Shannon bigram entropy
//
// Each kernel is benchmarked at the same three input sizes used elsewhere
// in this directory so the Performance Dashboard can compare apples to
// apples. Pure-STL signatures, no PYBIND11 — gated by XF_BENCH_MODE in
// the source files.

#include <benchmark/benchmark.h>

#include <random>
#include <string>
#include <vector>

#include "../anchor_descriptiveness.cpp"
#include "../anchor_self_information.cpp"
#include "../generic_anchor_matcher.cpp"

namespace {

std::string random_alpha(std::size_t length, std::mt19937& gen) {
    std::uniform_int_distribution<int> dis('a', 'z');
    std::string out;
    out.reserve(length);
    for (std::size_t i = 0; i < length; ++i) {
        out.push_back(static_cast<char>(dis(gen)));
        if (i % 6 == 5)
            out.push_back(' ');
    }
    return out;
}

}  // namespace

// ── anchor_descriptiveness ──────────────────────────────────────────

static void BM_DamerauLevenshtein(benchmark::State& state) {
    const std::size_t length = static_cast<std::size_t>(state.range(0));
    std::mt19937 gen(42);
    const std::string a = random_alpha(length, gen);
    const std::string b = random_alpha(length, gen);
    for (auto _ : state) {
        auto d = damerau_levenshtein(a, b);
        benchmark::DoNotOptimize(d);
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(length));
}
BENCHMARK(BM_DamerauLevenshtein)->Arg(20)->Arg(60)->Arg(180);

static void BM_CharTrigramJaccard(benchmark::State& state) {
    const std::size_t length = static_cast<std::size_t>(state.range(0));
    std::mt19937 gen(42);
    const std::string a = random_alpha(length, gen);
    const std::string b = random_alpha(length, gen);
    for (auto _ : state) {
        auto j = char_trigram_jaccard(a, b);
        benchmark::DoNotOptimize(j);
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(length));
}
BENCHMARK(BM_CharTrigramJaccard)->Arg(20)->Arg(60)->Arg(180);

// ── anchor_self_information ─────────────────────────────────────────

static void BM_BigramEntropy(benchmark::State& state) {
    const std::size_t length = static_cast<std::size_t>(state.range(0));
    std::mt19937 gen(42);
    const std::string text = random_alpha(length, gen);
    for (auto _ : state) {
        auto h = bigram_entropy(text);
        benchmark::DoNotOptimize(h);
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(length));
}
BENCHMARK(BM_BigramEntropy)->Arg(20)->Arg(120)->Arg(800);

// ── generic_anchor_matcher ──────────────────────────────────────────

static void BM_GenericAnchorBuild(benchmark::State& state) {
    const std::size_t n_phrases = static_cast<std::size_t>(state.range(0));
    std::mt19937 gen(42);
    std::vector<std::string> phrases;
    phrases.reserve(n_phrases);
    for (std::size_t i = 0; i < n_phrases; ++i) {
        phrases.push_back(random_alpha(8, gen));
    }
    for (auto _ : state) {
        auto aut = build_automaton(phrases);
        benchmark::DoNotOptimize(aut.get());
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n_phrases));
}
BENCHMARK(BM_GenericAnchorBuild)->Arg(50)->Arg(500)->Arg(5000);

static void BM_GenericAnchorFindAll(benchmark::State& state) {
    const std::size_t text_length = static_cast<std::size_t>(state.range(0));
    std::mt19937 gen(42);
    std::vector<std::string> phrases;
    for (std::size_t i = 0; i < 200; ++i) {
        phrases.push_back(random_alpha(8, gen));
    }
    auto aut = build_automaton(phrases);
    const std::string corpus = random_alpha(text_length, gen);
    for (auto _ : state) {
        const auto hits = find_all(aut, corpus);
        benchmark::DoNotOptimize(hits.size());
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(text_length));
}
BENCHMARK(BM_GenericAnchorFindAll)->Arg(200)->Arg(2000)->Arg(20000);

BENCHMARK_MAIN();
