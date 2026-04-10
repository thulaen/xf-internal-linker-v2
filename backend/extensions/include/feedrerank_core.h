#pragma once
#include <cstddef>
#include <cstdint>

void rerank_factors_core(
    const int32_t* successes, const int32_t* totals, size_t count,
    int n_global, double alpha, double beta, double weight,
    double exploration_rate, double* out_factors
);

void mmr_scores_core(
    const double* relevance, size_t candidate_count,
    const double* candidate_embeddings, const double* selected_embeddings,
    size_t selected_count, size_t embedding_width,
    double diversity_lambda,
    double* out_mmr_scores, double* out_max_similarities
);
