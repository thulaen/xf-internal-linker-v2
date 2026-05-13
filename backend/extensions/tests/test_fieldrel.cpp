#include <gtest/gtest.h>

#include <stdexcept>
#include <string>
#include <vector>

#include "fieldrel_core.h"

namespace {

double ScoreSampleField() {
    const std::vector<std::string> tokens = {"editor", "workflow", "links"};
    const std::vector<int> host_tfs = {1, 2, 1};
    const std::vector<int> field_tfs = {2, 1, 1};
    const std::vector<int> field_presence_counts = {1, 2, 3};
    return score_field_tokens(
        tokens,
        host_tfs,
        field_tfs,
        field_presence_counts,
        12,
        80.0,
        0.5,
        6,
        1.2,
        5);
}

}  // namespace

TEST(FieldRelTest, ScoresAlignedFieldTokens) {
    const double score = ScoreSampleField();

    EXPECT_GT(score, 0.0);
    EXPECT_LT(score, 1.0);
}

TEST(FieldRelTest, EmptyTokensStayNeutral) {
    const std::vector<std::string> tokens;
    const std::vector<int> values;

    EXPECT_DOUBLE_EQ(
        score_field_tokens(tokens, values, values, values, 0, 80.0, 0.5, 6, 1.2, 5),
        0.0);
}

TEST(FieldRelTest, MaxMatchedZeroStaysNeutral) {
    const std::vector<std::string> tokens = {"editor"};
    const std::vector<int> values = {1};

    EXPECT_DOUBLE_EQ(
        score_field_tokens(tokens, values, values, values, 1, 80.0, 0.5, 6, 1.2, 0),
        0.0);
}

TEST(FieldRelTest, RejectsMismatchedVectorSizes) {
    const std::vector<std::string> tokens = {"editor", "workflow"};
    const std::vector<int> one_value = {1};
    const std::vector<int> two_values = {1, 1};

    EXPECT_THROW(
        score_field_tokens(
            tokens, one_value, two_values, two_values, 2, 80.0, 0.5, 6, 1.2, 5),
        std::runtime_error);
}

TEST(FieldRelTest, HigherTermFrequencyRaisesScore) {
    const double low_score = score_field_tokens(
        {"editor"}, {1}, {1}, {1}, 1, 80.0, 0.5, 6, 1.2, 5);
    const double high_score = score_field_tokens(
        {"editor"}, {2}, {3}, {1}, 3, 80.0, 0.5, 6, 1.2, 5);

    EXPECT_GT(high_score, low_score);
}
