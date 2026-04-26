#include <vector>

#include "scoring_core.h"
#include "gtest/gtest.h"

// Test 1: zero rows — no crash
TEST(CscoreFullBatch, ZeroRows) {
  std::vector<float> weights = {1.0f};
  cscore_full_batch(nullptr, 0, 1, weights.data(), 1, nullptr, 0, nullptr);
}

// Test 2: single row, uniform weights
// out[0] = 0.2 + 0.5*0.5 + 0.5*0.5 = 0.7
TEST(CscoreFullBatch, SingleRowUniformWeights) {
  std::vector<float> components = {0.5f, 0.5f};
  std::vector<float> weights = {0.5f, 0.5f};
  std::vector<float> silo = {0.2f};
  std::vector<float> out(1, 0.0f);

  cscore_full_batch(components.data(), 1, 2, weights.data(), 2, silo.data(), 1,
                    out.data());

  EXPECT_NEAR(out[0], 0.7f, 1e-5f);
}

// Test 3: batch of 3 rows, first-component-dominant weight [1.0, 0.0]
// row 0: 0.1 + 0.8*1 + 0.5*0 = 0.9
// row 1: 0.0 + 0.4*1 + 0.9*0 = 0.4
// row 2: 0.5 + 0.2*1 + 0.3*0 = 0.7
TEST(CscoreFullBatch, BatchThreeRowsFirstComponentDominant) {
  std::vector<float> components = {0.8f, 0.5f, 0.4f, 0.9f, 0.2f, 0.3f};
  std::vector<float> weights = {1.0f, 0.0f};
  std::vector<float> silo = {0.1f, 0.0f, 0.5f};
  std::vector<float> out(3, 0.0f);

  cscore_full_batch(components.data(), 3, 2, weights.data(), 2, silo.data(), 3,
                    out.data());

  EXPECT_NEAR(out[0], 0.9f, 1e-5f);
  EXPECT_NEAR(out[1], 0.4f, 1e-5f);
  EXPECT_NEAR(out[2], 0.7f, 1e-5f);
}
