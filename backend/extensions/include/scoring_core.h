#pragma once
#include <cstddef>

extern "C" {
void cscore_full_batch(const float *component_scores, size_t num_rows,
                       size_t num_components, const float *weights,
                       size_t num_weights, const float *silo_scores,
                       size_t num_silo, float *out_scores);
}
