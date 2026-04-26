#pragma once
#include <cstddef>

void l2norm_normalize(float *data, size_t size);
void l2norm_normalize_batch(float *data, size_t rows, size_t cols);
