#include <cstdint>
#include <vector>

#include "gtest/gtest.h"
#include "quantemb_core.h"

// Test 1: Identity rotation, single vector
TEST(QuantEmbOPQ, IdentityRotationSingleVector) {
    const size_t dim = 4;
    const size_t m = 2;  // 2 subquantizers
    const size_t k = 4;  // 4 centroids per subquantizer
    const size_t sub_dim = 2;

    std::vector<float> vector = {1.0f, 0.0f, 0.0f, 1.0f};

    // Identity rotation
    std::vector<float> rotation = {1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1};

    // Codebooks: 2 subquantizers, 4 clusters each
    // Sub 0: [1,0], [0,1], [0.5,0.5], [0,0]
    // Sub 1: [1,0], [0,1], [0.5,0.5], [0,0]
    std::vector<float> codebooks = {
        // Subquantizer 0
        1.0f, 0.0f,  // k=0
        0.0f, 1.0f,  // k=1
        0.5f, 0.5f,  // k=2
        0.0f, 0.0f,  // k=3
        // Subquantizer 1
        1.0f, 0.0f,  // k=0
        0.0f, 1.0f,  // k=1
        0.5f, 0.5f,  // k=2
        0.0f, 0.0f   // k=3
    };

    std::vector<uint8_t> out_codes(m, 0);

    c_opq_encode(vector.data(), 1, dim, rotation.data(), codebooks.data(), m, k, out_codes.data());

    // Sub 0: [1,0] matches k=0
    // Sub 1: [0,1] matches k=1
    EXPECT_EQ(out_codes[0], 0);
    EXPECT_EQ(out_codes[1], 1);
}
