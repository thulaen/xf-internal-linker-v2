#include <vector>

#include "gtest/gtest.h"
#include "passagesim_core.h"

// Test 1: Empty matrix
TEST(PassageSimMaxSim, EmptyMatrix) {
  float query[] = {1.0f, 0.0f};
  float sim = -1.0f;
  size_t index = 999;
  c_passagesim_maxsim(query, nullptr, 0, 2, &sim, &index);
  EXPECT_EQ(sim, 0.0f);
  EXPECT_EQ(index, 0u);
}

// Test 2: Single passage, perfect match
TEST(PassageSimMaxSim, SinglePassagePerfectMatch) {
  std::vector<float> query = {1.0f, 0.0f, 0.0f};
  std::vector<float> matrix = {1.0f, 0.0f, 0.0f};
  float sim = 0.0f;
  size_t index = 999;
  c_passagesim_maxsim(query.data(), matrix.data(), 1, 3, &sim, &index);
  EXPECT_NEAR(sim, 1.0f, 1e-5f);
  EXPECT_EQ(index, 0u);
}

// Test 3: Multiple passages, find best match
TEST(PassageSimMaxSim, MultiplePassagesFindBest) {
  std::vector<float> query = {1.0f, 0.0f};
  // Passage 0: 0.5, 0.5 (sim ~0.707)
  // Passage 1: 0.0, 1.0 (sim 0.0)
  // Passage 2: 0.9, 0.1 (sim 0.9)
  std::vector<float> matrix = {0.5f, 0.5f, 0.0f, 1.0f, 0.9f, 0.1f};
  float sim = 0.0f;
  size_t index = 999;
  c_passagesim_maxsim(query.data(), matrix.data(), 3, 2, &sim, &index);
  EXPECT_NEAR(sim, 0.9f, 1e-5f);
  EXPECT_EQ(index, 2u);
}
