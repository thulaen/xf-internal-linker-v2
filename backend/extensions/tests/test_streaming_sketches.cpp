#include <gtest/gtest.h>

#include "../compressed_bloom.cpp"
#include "../count_min_sketch.cpp"
#include "../counting_bloom.cpp"

TEST(CountingBloomFilterTest, AddsAndRemovesItems) {
    CountingBloomFilter filter(4096, 4);
    filter.add("alpha");
    filter.add("beta");
    EXPECT_TRUE(filter.contains("alpha"));
    EXPECT_TRUE(filter.contains("beta"));
    filter.remove("alpha");
    EXPECT_FALSE(filter.contains("alpha"));
}

TEST(CompressedBloomFilterTest, KeepsFalsePositivesLowForSmokeSet) {
    CompressedBloomFilter filter(8192, 4);
    for (int i = 0; i < 100; ++i) {
        filter.add("seen-" + std::to_string(i));
    }
    int false_positives = 0;
    for (int i = 0; i < 100; ++i) {
        if (filter.contains("unseen-" + std::to_string(i))) {
            ++false_positives;
        }
    }
    EXPECT_LE(false_positives, 5);
}

TEST(CountMinSketchTest, EstimatesWithoutUndercounting) {
    CountMinSketch sketch(1024, 5);
    sketch.add("alpha", 7);
    sketch.add("beta", 3);
    EXPECT_GE(sketch.estimate("alpha"), 7U);
    EXPECT_GE(sketch.estimate("beta"), 3U);
    EXPECT_EQ(sketch.estimate("missing"), 0U);
}
