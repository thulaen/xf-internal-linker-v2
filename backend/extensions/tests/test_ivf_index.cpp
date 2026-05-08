#include <cstdint>
#include <vector>

#include "gtest/gtest.h"
#include "ivf_index_core.h"

// Test 1: Find top centroids — single nearest match.
TEST(IvfFindTopCentroids, SingleNearestMatch) {
    // Two centroids in 2D: one at origin, one at (10, 10).
    // Query at (1, 1) is closer to origin.
    std::vector<float> centroids = {0.0f, 0.0f, 10.0f, 10.0f};
    float query[] = {1.0f, 1.0f};
    int32_t out_ids[1] = {-1};
    float out_dists[1] = {-1.0f};

    c_ivf_find_top_centroids(query, centroids.data(), 2, 2, 1, out_ids, out_dists);

    EXPECT_EQ(out_ids[0], 0);
    EXPECT_NEAR(out_dists[0], 2.0f, 1e-5f);
}

// Test 2: Find top centroids — order-stable for ties.
TEST(IvfFindTopCentroids, ReturnsSortedAscending) {
    // Three centroids; query equidistant from 0 and 1, farther from 2.
    std::vector<float> centroids = {1.0f, 0.0f, -1.0f, 0.0f, 0.0f, 5.0f};
    float query[] = {0.0f, 0.0f};
    int32_t out_ids[3] = {-1, -1, -1};
    float out_dists[3] = {-1.0f, -1.0f, -1.0f};

    c_ivf_find_top_centroids(query, centroids.data(), 3, 2, 3, out_ids, out_dists);

    // Distances: 1.0, 1.0, 25.0. Top-3 returned in ascending dist order.
    EXPECT_NEAR(out_dists[0], 1.0f, 1e-5f);
    EXPECT_NEAR(out_dists[1], 1.0f, 1e-5f);
    EXPECT_NEAR(out_dists[2], 25.0f, 1e-5f);
    EXPECT_EQ(out_ids[2], 2);
}

// Test 3: Build ADC LUT — identity rotation reduces to PQ.
TEST(IvfBuildAdcLut, IdentityRotationMatchesPlainPq) {
    // dim=4, m=2, k=2, sub_dim=2.
    // Identity rotation, simple codebooks.
    std::vector<float> rotation = {
        1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f, 0.0f, 0.0f,
        0.0f, 0.0f, 1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f,
    };
    // codebooks shape (m=2, k=2, sub_dim=2)
    // m=0: centroid 0 = (0,0), centroid 1 = (1,0)
    // m=1: centroid 0 = (0,0), centroid 1 = (0,1)
    std::vector<float> codebooks = {
        0.0f, 0.0f, 1.0f, 0.0f, 0.0f, 0.0f, 0.0f, 1.0f,
    };
    // query = (1, 0, 0, 1) — sub_q[0] = (1, 0); sub_q[1] = (0, 1)
    std::vector<float> query = {1.0f, 0.0f, 0.0f, 1.0f};
    std::vector<float> lut(4, -1.0f);

    c_ivf_build_adc_lut(query.data(), rotation.data(), codebooks.data(), 4, 2, 2, lut.data());

    // sub_q[0]=(1,0): dist to centroid0=(0,0) is 1, to centroid1=(1,0) is 0.
    EXPECT_NEAR(lut[0], 1.0f, 1e-5f);
    EXPECT_NEAR(lut[1], 0.0f, 1e-5f);
    // sub_q[1]=(0,1): dist to centroid0=(0,0) is 1, to centroid1=(0,1) is 0.
    EXPECT_NEAR(lut[2], 1.0f, 1e-5f);
    EXPECT_NEAR(lut[3], 0.0f, 1e-5f);
}

// Test 4: ADC distance — sums LUT entries indexed by code bytes.
TEST(IvfAdcDistance, SumsLutEntriesByCode) {
    // m=2, k=2, LUT row-major: [lut[0,0], lut[0,1], lut[1,0], lut[1,1]]
    std::vector<float> lut = {1.5f, 0.5f, 2.0f, 0.25f};
    // code = [1, 0] → lut[0,1] + lut[1,0] = 0.5 + 2.0 = 2.5
    uint8_t code[] = {1, 0};
    float dist = c_ivf_adc_distance(code, lut.data(), 2, 2);
    EXPECT_NEAR(dist, 2.5f, 1e-5f);

    // code = [0, 1] → lut[0,0] + lut[1,1] = 1.5 + 0.25 = 1.75
    code[0] = 0;
    code[1] = 1;
    dist = c_ivf_adc_distance(code, lut.data(), 2, 2);
    EXPECT_NEAR(dist, 1.75f, 1e-5f);
}

// Test 5: Degenerate input — m=0 yields zero-LUT, no crash.
TEST(IvfBuildAdcLut, ZeroSubquantisersDoesNotCrash) {
    std::vector<float> query = {1.0f};
    std::vector<float> rotation = {1.0f};
    std::vector<float> codebooks = {0.0f};
    // m=0 means LUT length 0 — function should early-return safely.
    std::vector<float> lut;
    c_ivf_build_adc_lut(query.data(), rotation.data(), codebooks.data(), 1, 0, 0, lut.data());
    // No assertion on the (empty) LUT contents — survival is the contract.
    SUCCEED();
}
