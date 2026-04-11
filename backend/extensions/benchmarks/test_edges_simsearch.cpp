/* Edge-case unit tests for cscore_and_topk.
 *
 * Key invariant verified throughout:
 *   out_indices[i] is a POSITION in the candidate array (0 .. candidate_count-1),
 *   NOT a raw sentence-matrix row number.
 *   The caller maps positions back to row numbers via candidate_rows[out_indices[i]].
 *
 * Built under XF_BENCH_MODE (defined by CMakeLists.txt), so the pybind11
 * PYBIND11_MODULE block inside simsearch.cpp is excluded.
 */
#include <cassert>
#include <cmath>
#include <cstdint>
#include <cstdio>
#include <limits>
#include <vector>

#include "simsearch_core.h"

namespace {

/* Populate a unit-norm destination vector of length dim. */
std::vector<float> unit_dest(std::size_t dim) {
    std::vector<float> d(dim, 0.0f);
    if (dim > 0) {
        d[0] = 1.0f; /* only first component non-zero */
    }
    return d;
}

/* ── Test 1: empty candidate list returns out_count = 0 ─────────────────── */
void test_empty_candidates() {
    const std::size_t dim = 4;
    auto dest = unit_dest(dim);
    std::vector<float> sentences(dim, 1.0f);

    std::vector<int64_t> out_indices(10);
    std::vector<float> out_scores(10);
    std::size_t out_count = 999;

    cscore_and_topk(dest.data(), dim, sentences.data(), 1, dim,
                    /* candidate_rows */ nullptr, /* candidate_count */ 0,
                    /* top_k */ 5, out_indices.data(), out_scores.data(), &out_count);

    assert(out_count == 0 && "empty candidates must yield out_count == 0");
    std::puts("PASS test_empty_candidates");
}

/* ── Test 2: top_k == 0 returns out_count = 0 ───────────────────────────── */
void test_zero_topk() {
    const std::size_t dim = 4;
    auto dest = unit_dest(dim);
    std::vector<float> sentences(dim, 1.0f);
    std::vector<int32_t> rows = {0};

    std::vector<int64_t> out_indices(10);
    std::vector<float> out_scores(10);
    std::size_t out_count = 999;

    cscore_and_topk(dest.data(), dim, sentences.data(), 1, dim, rows.data(), 1,
                    /* top_k */ 0, out_indices.data(), out_scores.data(), &out_count);

    assert(out_count == 0 && "top_k == 0 must yield out_count == 0");
    std::puts("PASS test_zero_topk");
}

/* ── Test 3: single candidate, top_k == 1 ───────────────────────────────── */
void test_single_candidate() {
    const std::size_t dim = 4;
    /* dest = [1, 0, 0, 0]; sentence row 0 = [0.5, 0, 0, 0] => score = 0.5 */
    auto dest = unit_dest(dim);
    std::vector<float> sentences(dim, 0.0f);
    sentences[0] = 0.5f;

    std::vector<int32_t> rows = {0};
    std::vector<int64_t> out_indices(5);
    std::vector<float> out_scores(5);
    std::size_t out_count = 0;

    cscore_and_topk(dest.data(), dim, sentences.data(), 1, dim, rows.data(), 1, 1,
                    out_indices.data(), out_scores.data(), &out_count);

    assert(out_count == 1);
    /* out_indices[0] is a POSITION in the candidate array, so must be 0 */
    assert(out_indices[0] == 0 && "position in candidate array must be 0 for single candidate");
    assert(std::fabs(out_scores[0] - 0.5f) < 1e-5f);
    std::puts("PASS test_single_candidate");
}

/* ── Test 4: top_k larger than candidate_count clamps to candidate_count ── */
void test_topk_clamp() {
    const std::size_t dim = 2;
    /* two candidates, ask for 100 */
    std::vector<float> dest = {1.0f, 0.0f};
    std::vector<float> sentences = {0.9f, 0.0f, 0.1f, 0.0f}; /* row 0 and row 1 */
    std::vector<int32_t> rows = {0, 1};

    std::vector<int64_t> out_indices(200);
    std::vector<float> out_scores(200);
    std::size_t out_count = 0;

    cscore_and_topk(dest.data(), dim, sentences.data(), 2, dim, rows.data(), 2, 100,
                    out_indices.data(), out_scores.data(), &out_count);

    assert(out_count == 2 && "clamped to candidate_count == 2");
    std::puts("PASS test_topk_clamp");
}

/* ── Test 5: ordering — best score must appear first (position invariant) ── */
void test_ordering() {
    const std::size_t dim = 1;
    /* dest = [1]; candidates mapped to rows with known scores */
    std::vector<float> dest = {1.0f};
    /* sentence matrix: 5 rows with scores 0.1, 0.5, 0.9, 0.3, 0.7 */
    std::vector<float> sentences = {0.1f, 0.5f, 0.9f, 0.3f, 0.7f};
    /* present all 5 as candidates in their natural order */
    std::vector<int32_t> rows = {0, 1, 2, 3, 4};

    std::vector<int64_t> out_indices(5);
    std::vector<float> out_scores(5);
    std::size_t out_count = 0;

    cscore_and_topk(dest.data(), dim, sentences.data(), 5, dim, rows.data(), 5, 3,
                    out_indices.data(), out_scores.data(), &out_count);

    assert(out_count == 3);
    /* Expected positions in candidate array (0-based) for top-3: row 2(pos2)=0.9,
     * row 4(pos4)=0.7, row 1(pos1)=0.5 */
    assert(out_indices[0] == 2); /* highest score: position 2 -> row 2 */
    assert(out_indices[1] == 4); /* second: position 4 -> row 4 */
    assert(out_indices[2] == 1); /* third: position 1 -> row 1 */
    assert(out_scores[0] > out_scores[1]);
    assert(out_scores[1] > out_scores[2]);
    std::puts("PASS test_ordering");
}

/* ── Test 6: NaN in sentence data — no crash, guard only ────────────────── */
void test_nan_in_sentences() {
    const std::size_t dim = 2;
    std::vector<float> dest = {1.0f, 0.0f};
    /* row 0 has NaN in dimension 0 */
    std::vector<float> sentences = {std::numeric_limits<float>::quiet_NaN(), 0.0f};
    std::vector<int32_t> rows = {0};

    std::vector<int64_t> out_indices(5);
    std::vector<float> out_scores(5);
    std::size_t out_count = 0;

    /* Must not crash; score value for a NaN row is implementation-defined */
    cscore_and_topk(dest.data(), dim, sentences.data(), 1, dim, rows.data(), 1, 1,
                    out_indices.data(), out_scores.data(), &out_count);

    assert(out_count == 1 && "NaN input must not crash; out_count still 1");
    std::puts("PASS test_nan_in_sentences (no crash)");
}

/* ── Test 7: large n = 10 000 candidates completes without error ─────────── */
void test_large_n() {
    const std::size_t dim = 16;
    const std::size_t n = 10000;

    std::vector<float> dest(dim, 1.0f / static_cast<float>(dim));
    std::vector<float> sentences(n * dim, 0.5f);
    std::vector<int32_t> rows(n);
    for (std::size_t i = 0; i < n; ++i) {
        rows[i] = static_cast<int32_t>(i);
    }

    std::vector<int64_t> out_indices(50);
    std::vector<float> out_scores(50);
    std::size_t out_count = 0;

    cscore_and_topk(dest.data(), dim, sentences.data(), n, dim, rows.data(), n, 50,
                    out_indices.data(), out_scores.data(), &out_count);

    assert(out_count == 50 && "must return exactly top_k == 50 for n=10000");
    /* Every row has the same score, so all positions are equally valid;
     * just verify scores are finite and non-negative. */
    for (std::size_t i = 0; i < out_count; ++i) {
        assert(std::isfinite(out_scores[i]));
        assert(out_scores[i] >= 0.0f);
    }
    std::puts("PASS test_large_n");
}

} /* namespace */

int main() {
    test_empty_candidates();
    test_zero_topk();
    test_single_candidate();
    test_topk_clamp();
    test_ordering();
    test_nan_in_sentences();
    test_large_n();
    std::puts("ALL simsearch edge tests PASSED");
    return 0;
}
