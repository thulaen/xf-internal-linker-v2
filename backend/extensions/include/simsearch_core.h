#pragma once
#include <cstddef>
#include <cstdint>

extern "C" {
void cscore_and_topk(const float* destination_ptr, size_t dest_dim, const float* sentence_ptr,
                     size_t num_sentences, size_t sentence_dim, const int32_t* candidate_rows,
                     size_t candidate_count, int top_k, int64_t* out_indices, float* out_scores,
                     size_t* out_count);
}
