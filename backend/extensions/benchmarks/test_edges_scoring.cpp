/* Edge-case unit tests for cscore_full_batch.
 *
 * Formula under test (from scoring.cpp):
 *   out[row] = silo[row] + sum_over_cols( component[row][col] * weights[col] )
 *
 * Built under XF_BENCH_MODE (defined by CMakeLists.txt), so the pybind11
 * PYBIND11_MODULE block inside scoring.cpp is excluded.
 */
#include <cassert>
#include <cmath>
#include <cstddef>
#include <cstdio>
#include <limits>
#include <vector>

#include "scoring_core.h"

namespace {

static constexpr float kTol = 1e-5f;

/* ── Test 1: zero rows — must not crash ─────────────────────────────────── */
void test_zero_rows() {
    std::vector<float> components;
    std::vector<float> weights = {1.0f};
    std::vector<float> silo;
    std::vector<float> out;

    /* Passing nullptr with zero sizes should be a no-op, not UB */
    cscore_full_batch(nullptr, 0, 1, weights.data(), 1, nullptr, 0, nullptr);
    std::puts("PASS test_zero_rows");
}

/* ── Test 2: single row, single component ───────────────────────────────── */
void test_single_row_single_component() {
    /* out[0] = silo[0] + component[0][0] * weights[0] = 0.3 + 0.7 * 2.0 = 1.7 */
    std::vector<float> components = {0.7f};
    std::vector<float> weights = {2.0f};
    std::vector<float> silo = {0.3f};
    std::vector<float> out(1, 0.0f);

    cscore_full_batch(components.data(), 1, 1, weights.data(), 1, silo.data(), 1, out.data());

    assert(std::fabs(out[0] - 1.7f) < kTol);
    std::puts("PASS test_single_row_single_component");
}

/* ── Test 3: multiple rows, multiple components ──────────────────────────── */
void test_multi_row_multi_component() {
    /* 3 rows, 2 components, weights = [1.0, 2.0]
     * row 0: silo=0.0, comp=[1.0, 1.0] -> 0 + 1*1 + 1*2 = 3.0
     * row 1: silo=1.0, comp=[0.5, 0.5] -> 1 + 0.5*1 + 0.5*2 = 2.5
     * row 2: silo=0.5, comp=[2.0, 0.0] -> 0.5 + 2*1 + 0*2 = 2.5
     */
    std::vector<float> components = {1.0f, 1.0f, 0.5f, 0.5f, 2.0f, 0.0f};
    std::vector<float> weights = {1.0f, 2.0f};
    std::vector<float> silo = {0.0f, 1.0f, 0.5f};
    std::vector<float> out(3, 0.0f);

    cscore_full_batch(components.data(), 3, 2, weights.data(), 2, silo.data(), 3, out.data());

    assert(std::fabs(out[0] - 3.0f) < kTol);
    assert(std::fabs(out[1] - 2.5f) < kTol);
    assert(std::fabs(out[2] - 2.5f) < kTol);
    std::puts("PASS test_multi_row_multi_component");
}

/* ── Test 4: all-zero weights produce silo passthrough ─────────────────── */
void test_zero_weights() {
    std::vector<float> components = {9.9f, 8.8f, 7.7f};
    std::vector<float> weights = {0.0f, 0.0f, 0.0f};
    std::vector<float> silo = {3.14f};
    std::vector<float> out(1, 0.0f);

    cscore_full_batch(components.data(), 1, 3, weights.data(), 3, silo.data(), 1, out.data());

    assert(std::fabs(out[0] - 3.14f) < kTol);
    std::puts("PASS test_zero_weights");
}

/* ── Test 5: all-zero silo produces pure weighted-sum ───────────────────── */
void test_zero_silo() {
    /* out[0] = 0.0 + 2.0 * 3.0 = 6.0 */
    std::vector<float> components = {2.0f};
    std::vector<float> weights = {3.0f};
    std::vector<float> silo = {0.0f};
    std::vector<float> out(1, 0.0f);

    cscore_full_batch(components.data(), 1, 1, weights.data(), 1, silo.data(), 1, out.data());

    assert(std::fabs(out[0] - 6.0f) < kTol);
    std::puts("PASS test_zero_silo");
}

/* ── Test 6: mismatch guard — num_components != num_weights must no-op ──── */
void test_mismatch_guard() {
    std::vector<float> components = {1.0f, 2.0f};
    std::vector<float> weights = {1.0f}; /* length 1, but 2 components */
    std::vector<float> silo = {5.0f};
    std::vector<float> out = {99.0f}; /* sentinel */

    cscore_full_batch(components.data(), 1, 2, weights.data(), 1, silo.data(), 1, out.data());

    /* Implementation returns without writing when sizes mismatch;
     * sentinel must be unchanged. */
    assert(std::fabs(out[0] - 99.0f) < kTol && "mismatch must leave output unchanged");
    std::puts("PASS test_mismatch_guard");
}

/* ── Test 7: large n = 100 000 rows completes without error ─────────────── */
void test_large_n() {
    const std::size_t n = 100000;
    const std::size_t k = 4;

    std::vector<float> components(n * k, 1.0f);
    std::vector<float> weights(k, 0.25f); /* weighted sum = k * 1.0 * 0.25 = 1.0 */
    std::vector<float> silo(n, 0.5f);    /* each out[i] = 0.5 + 1.0 = 1.5 */
    std::vector<float> out(n, 0.0f);

    cscore_full_batch(components.data(), n, k, weights.data(), k, silo.data(), n, out.data());

    for (std::size_t i = 0; i < n; ++i) {
        assert(std::fabs(out[i] - 1.5f) < kTol);
    }
    std::puts("PASS test_large_n");
}

/* ── Test 8: negative silo and negative weights produce correct sign ─────── */
void test_negative_values() {
    /* out[0] = -1.0 + (-2.0) * 3.0 = -7.0 */
    std::vector<float> components = {-2.0f};
    std::vector<float> weights = {3.0f};
    std::vector<float> silo = {-1.0f};
    std::vector<float> out(1, 0.0f);

    cscore_full_batch(components.data(), 1, 1, weights.data(), 1, silo.data(), 1, out.data());

    assert(std::fabs(out[0] - (-7.0f)) < kTol);
    std::puts("PASS test_negative_values");
}

} /* namespace */

int main() {
    test_zero_rows();
    test_single_row_single_component();
    test_multi_row_multi_component();
    test_zero_weights();
    test_zero_silo();
    test_mismatch_guard();
    test_large_n();
    test_negative_values();
    std::puts("ALL scoring edge tests PASSED");
    return 0;
}
