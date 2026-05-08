#pragma once
#include <cstddef>
#include <cstdint>

extern "C" {
/**
 * Perform OPQ encoding on a batch of vectors.
 *
 * @param vectors_ptr Pointer to the matrix of input vectors (float[num_vectors * dim])
 * @param num_vectors Number of vectors to encode
 * @param dim Dimension of the vectors
 * @param rotation_ptr Pointer to the OPQ rotation matrix (float[dim * dim])
 * @param codebooks_ptr Pointer to the product quantization codebooks (float[m * k * (dim/m)])
 * @param m Number of subquantizers
 * @param k Number of centroids per subquantizer
 * @param out_codes Pointer to store the resulting quantized codes (uint8_t[num_vectors * m])
 */
void c_opq_encode(const float* vectors_ptr, size_t num_vectors, size_t dim,
                  const float* rotation_ptr, const float* codebooks_ptr, size_t m, size_t k,
                  uint8_t* out_codes);
}
