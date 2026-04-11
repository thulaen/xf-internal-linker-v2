#pragma once
#include <cstddef>
#include <cstdint>

double pagerank_step_core(const int32_t* indptr, const int32_t* indices, const double* data,
                          const double* ranks, const bool* dangling_mask, double damping,
                          int node_count, double* out_next_ranks);
