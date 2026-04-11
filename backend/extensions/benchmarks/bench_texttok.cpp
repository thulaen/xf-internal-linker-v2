#include <benchmark/benchmark.h>

#include <string>
#include <unordered_set>
#include <vector>

#include "bench_common.h"
#include "texttok_core.h"

namespace {

std::unordered_set<std::string> make_stopwords() {
    return {"the",   "a",      "an",   "is",    "are", "was",   "were", "be",   "been",
            "being", "have",   "has",  "had",   "do",  "does",  "did",  "will", "would",
            "could", "should", "may",  "might", "can", "shall", "to",   "of",   "in",
            "for",   "on",     "with", "at",    "by",  "from"};
}

std::vector<std::string> make_texts(size_t n, unsigned seed = 42) {
    auto tokens = xf_bench::random_tokens(n * 20, 10, seed);
    std::vector<std::string> texts;
    texts.reserve(n);
    for (size_t i = 0; i < n; ++i) {
        std::string text;
        for (size_t j = 0; j < 20; ++j) {
            if (j > 0)
                text.push_back(' ');
            text += tokens[i * 20 + j];
        }
        texts.push_back(text);
    }
    return texts;
}

void BM_TokenizeBatch(benchmark::State& state) {
    const auto n = static_cast<size_t>(state.range(0));
    auto texts = make_texts(n, 42);
    auto stopwords = make_stopwords();

    for (auto _ : state) {
        auto results = tokenize_text_batch_core(texts, stopwords);
        benchmark::DoNotOptimize(results);
    }
    state.SetItemsProcessed(state.iterations() * static_cast<int64_t>(n));
}
BENCHMARK(BM_TokenizeBatch)->Arg(10)->Arg(1000)->Arg(10000);

}  // namespace
