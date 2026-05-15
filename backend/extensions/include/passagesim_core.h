#pragma once
#include <cstddef>

extern "C" {
/**
 * Compute the maximum cosine similarity between a query vector and a matrix of
 * passage vectors.
 *
 * @param query_ptr Pointer to the query vector (float[dim])
 * @param matrix_ptr Pointer to the matrix of passage vectors
 * (float[num_passages * dim])
 * @param num_passages Number of passage vectors in the matrix
 * @param dim Dimension of the vectors
 * @param out_sim Pointer to store the maximum similarity score
 * @param out_index Pointer to store the index of the best matching passage
 */
void c_passagesim_maxsim(const float* query_ptr, const float* matrix_ptr,
                         size_t num_passages, size_t dim, float* out_sim,
                         size_t* out_index);
}
