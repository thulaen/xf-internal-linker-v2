#include <cmath>
#include <cstdint>
#include <vector>

#include "gtest/gtest.h"
#include "quantemb_core.h"

// Test 1: Identity rotation, single vector
TEST(QuantEmbOPQ, IdentityRotationSingleVector) {
  const size_t dim = 4;
  const size_t m = 2;  // 2 subquantizers
  const size_t k = 4;  // 4 centroids per subquantizer

  std::vector<float> vector = {1.0f, 0.0f, 0.0f, 1.0f};

  // Identity rotation
  std::vector<float> rotation = {1, 0, 0, 0, 0, 1, 0, 0,
                                 0, 0, 1, 0, 0, 0, 0, 1};

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

  c_opq_encode(vector.data(), 1, dim, rotation.data(), codebooks.data(), m, k,
               out_codes.data());

  // Sub 0: [1,0] matches k=0
  // Sub 1: [0,1] matches k=1
  EXPECT_EQ(out_codes[0], 0);
  EXPECT_EQ(out_codes[1], 1);
}

TEST(QuantEmbOPQ, TrainIdentityKMeansProducesUsableCodebooks) {
  const size_t num_vectors = 4;
  const size_t dim = 4;
  const size_t m = 2;
  const size_t k = 2;
  const size_t sub_dim = dim / m;

  std::vector<float> vectors = {
      1.0f, 0.0f, 0.0f, 1.0f, 0.9f, 0.1f, 0.1f, 0.9f,
      0.0f, 1.0f, 1.0f, 0.0f, 0.1f, 0.9f, 0.9f, 0.1f,
  };
  std::vector<float> rotation(dim * dim, 0.0f);
  std::vector<float> codebooks(m * k * sub_dim, 0.0f);
  std::vector<uint8_t> out_codes(num_vectors * m, 0);

  c_opq_train_identity_kmeans(vectors.data(), num_vectors, dim, m, k, 4,
                              rotation.data(), codebooks.data());
  c_opq_encode(vectors.data(), num_vectors, dim, rotation.data(),
               codebooks.data(), m, k, out_codes.data());

  EXPECT_FLOAT_EQ(rotation[0], 1.0f);
  EXPECT_FLOAT_EQ(rotation[5], 1.0f);
  EXPECT_FLOAT_EQ(rotation[10], 1.0f);
  EXPECT_FLOAT_EQ(rotation[15], 1.0f);
  for (uint8_t code : out_codes) {
    EXPECT_LT(code, k);
  }
}

TEST(QuantEmbOPQ, TrainKMeansSkipsEmptyClusters) {
  // Cover the `if (counts[k_idx] == 0) continue;` branch in
  // `update_centroids_kmeans`: train with k=4 codewords but only 2
  // distinct input vectors per subquantizer, so at least two clusters
  // end up with zero assignments. The function must leave those empty
  // centroids unchanged rather than divide by zero.
  const size_t num_vectors = 2;
  const size_t dim = 4;
  const size_t m = 2;
  const size_t k = 4;
  std::vector<float> vectors = {
      1.0f, 0.0f, 1.0f, 0.0f, 0.0f, 1.0f, 0.0f, 1.0f,
  };
  std::vector<float> rotation(dim * dim, 0.0f);
  std::vector<float> codebooks(m * k * (dim / m), 0.0f);
  c_opq_train_identity_kmeans(vectors.data(), num_vectors, dim, m, k, 2,
                              rotation.data(), codebooks.data());
  // No NaN/Inf in codebooks (would happen if we divided by zero count).
  for (float v : codebooks) {
    EXPECT_TRUE(std::isfinite(v));
  }
}
