#pragma once
#include <cstddef>
#include <cstdint>

extern "C" {
/**
 * Perform OPQ encoding on a batch of vectors.
 *
 * @param vectors_ptr Pointer to the matrix of input vectors (float[num_vectors
 * * dim])
 * @param num_vectors Number of vectors to encode
 * @param dim Dimension of the vectors
 * @param rotation_ptr Pointer to the OPQ rotation matrix (float[dim * dim])
 * @param codebooks_ptr Pointer to the product quantization codebooks (float[m *
 * k * (dim/m)])
 * @param m Number of subquantizers
 * @param k Number of centroids per subquantizer
 * @param out_codes Pointer to store the resulting quantized codes
 * (uint8_t[num_vectors * m])
 */
void c_opq_encode(const float* vectors_ptr, size_t num_vectors, size_t dim,
                  const float* rotation_ptr, const float* codebooks_ptr,
                  size_t m, size_t k, uint8_t* out_codes);

/**
 * Train deterministic product-quantization codebooks with an identity OPQ
 * rotation. The identity rotation keeps the existing encoder contract while
 * leaving a single compiled entry point for a later learned rotation step.
 *
 * @param vectors_ptr Pointer to the matrix of input vectors (float[num_vectors
 * * dim])
 * @param num_vectors Number of vectors in the training sample
 * @param dim Dimension of each vector
 * @param m Number of subquantizers
 * @param k Number of centroids per subquantizer
 * @param n_iter Number of k-means refinement passes
 * @param rotation_ptr Output identity rotation matrix (float[dim * dim])
 * @param codebooks_ptr Output codebooks (float[m * k * (dim/m)])
 */
void c_opq_train_identity_kmeans(const float* vectors_ptr, size_t num_vectors,
                                 size_t dim, size_t m, size_t k, size_t n_iter,
                                 float* rotation_ptr, float* codebooks_ptr);
}
