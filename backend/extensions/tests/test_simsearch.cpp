#include <cstdint>
#include <vector>

#include "gtest/gtest.h"
#include "simsearch_core.h"

// Test 1: zero candidates — out_count == 0, no crash
TEST(CscoreAndTopk, ZeroCandidates) {
    const size_t dim = 4;
    std::vector<float> dest = {1.0f, 0.0f, 0.0f, 0.0f};
    std::vector<float> sentences(dim, 1.0f);
    std::vector<int64_t> out_indices(10);
    std::vector<float> out_scores(10);
    size_t out_count = 999;

    cscore_and_topk(dest.data(), dim, sentences.data(), 1, dim, nullptr, 0, 5, out_indices.data(),
                    out_scores.data(), &out_count);

    EXPECT_EQ(out_count, 0u);
}

// Test 2: single candidate, perfect dot product
TEST(CscoreAndTopk, SingleCandidatePerfectDot) {
    const size_t dim = 4;
    std::vector<float> dest = {1.0f, 0.0f, 0.0f, 0.0f};
    std::vector<float> sentences = {1.0f, 0.0f, 0.0f, 0.0f};
    std::vector<int32_t> rows = {0};
    std::vector<int64_t> out_indices(5);
    std::vector<float> out_scores(5);
    size_t out_count = 0;

    cscore_and_topk(dest.data(), dim, sentences.data(), 1, dim, rows.data(), 1, 1,
                    out_indices.data(), out_scores.data(), &out_count);

    EXPECT_EQ(out_count, 1u);
    EXPECT_EQ(out_indices[0], 0);  // position 0 in candidate array
    EXPECT_NEAR(out_scores[0], 1.0f, 1e-5f);
}

// Test 3: 3 candidates, top-2 returned in score-descending order
TEST(CscoreAndTopk, ThreeCandidatesTopTwo) {
    const size_t dim = 1;
    std::vector<float> dest = {1.0f};
    // row 0 = 0.3, row 1 = 0.9, row 2 = 0.6
    std::vector<float> sentences = {0.3f, 0.9f, 0.6f};
    std::vector<int32_t> rows = {0, 1, 2};
    std::vector<int64_t> out_indices(5);
    std::vector<float> out_scores(5);
    size_t out_count = 0;

    cscore_and_topk(dest.data(), dim, sentences.data(), 3, dim, rows.data(), 3, 2,
                    out_indices.data(), out_scores.data(), &out_count);

    EXPECT_EQ(out_count, 2u);
    EXPECT_EQ(out_indices[0], 1);  // candidate position 1 (row 1, score 0.9) is best
    EXPECT_EQ(out_indices[1], 2);  // candidate position 2 (row 2, score 0.6) is second
    EXPECT_GT(out_scores[0], out_scores[1]);
    EXPECT_NEAR(out_scores[0], 0.9f, 1e-5f);
    EXPECT_NEAR(out_scores[1], 0.6f, 1e-5f);
}
