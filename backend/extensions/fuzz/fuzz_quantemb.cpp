// libFuzzer harness for the OPQ encoding kernel in quantemb.cpp.

#include <cstddef>
#include <cstdint>
#include <vector>

#include "include/quantemb_core.h"

namespace {
constexpr size_t kMaxVectors = 8;
constexpr size_t kMaxSubquantizers = 4;
constexpr size_t kMaxSubDim = 8;
constexpr size_t kMaxCentroids = 16;
}  // namespace

extern "C" int LLVMFuzzerTestOneInput(const uint8_t* data, size_t size) {
    if (size < 4) {
        return 0;
    }

    const size_t num_vectors = 1 + (data[0] % kMaxVectors);
    const size_t m = 1 + (data[1] % kMaxSubquantizers);
    const size_t sub_dim = 1 + (data[2] % kMaxSubDim);
    const size_t k = 1 + (data[3] % kMaxCentroids);
    const size_t dim = m * sub_dim;

    const size_t vector_count = num_vectors * dim;
    const size_t rotation_count = dim * dim;
    const size_t codebook_count = m * k * sub_dim;
    const size_t total_floats = vector_count + rotation_count + codebook_count;
    const size_t needed = 4 + total_floats * sizeof(float);
    if (size < needed) {
        return 0;
    }

    const float* floats = reinterpret_cast<const float*>(data + 4);
    const float* vectors = floats;
    const float* rotation = vectors + vector_count;
    const float* codebooks = rotation + rotation_count;
    std::vector<uint8_t> out_codes(num_vectors * m);

    c_opq_encode(vectors, num_vectors, dim, rotation, codebooks, m, k, out_codes.data());
    return out_codes.empty() ? 1 : 0;
}
