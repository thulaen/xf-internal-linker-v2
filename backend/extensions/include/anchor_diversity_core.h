#pragma once
#include <cstddef>
#include <cstdint>

// FR-045 anchor diversity / exact-match reuse guard — C++ batch fast path.
// Mirrors the Python reference in
// backend/apps/pipeline/services/anchor_diversity.py::evaluate_anchor_diversity
// at 1e-6 parity. Python still owns normalization (regex with \w Unicode
// semantics) and diagnostics-dict composition; C++ only handles the
// arithmetic inner loop so the per-candidate hot path amortises across
// a pybind11 batch call.
//
// State index encoding (mirrors Python `anchor_diversity_state`):
//   1 = neutral_no_history
//   2 = neutral_below_threshold
//   3 = penalized_exact_share
//   4 = penalized_exact_count
//   5 = blocked_exact_count
// Python handles states 0 (disabled) and 6 (neutral_no_anchor) before
// delegating to C++.

void evaluate_anchor_diversity_core(
    const int32_t *active_anchor_counts,
    const int32_t *exact_match_counts_before, std::size_t count,
    int32_t min_history_count, double max_exact_match_share,
    int32_t max_exact_match_count, bool hard_cap_enabled,
    int32_t *out_projected_exact_count, double *out_projected_exact_share,
    double *out_share_overflow, double *out_count_overflow_norm,
    double *out_spam_risk, double *out_score_anchor_diversity,
    int32_t *out_state_index, uint8_t *out_would_block);
