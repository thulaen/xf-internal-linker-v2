#ifndef XF_BENCH_MODE
#include <pybind11/numpy.h>
#include <pybind11/pybind11.h>
namespace py = pybind11;
#endif

#include <algorithm>
#include <cstddef>
#include <cstdint>
#include <stdexcept>

#include "include/anchor_diversity_core.h"

// FR-045 state-index constants (mirror the Python
// `anchor_diversity_state` enum). Module-local so nothing depends on
// their exact integer values — Python maps them back to strings.
namespace {
constexpr int32_t STATE_NEUTRAL_NO_HISTORY = 1;
constexpr int32_t STATE_NEUTRAL_BELOW_THRESHOLD = 2;
constexpr int32_t STATE_PENALIZED_EXACT_SHARE = 3;
constexpr int32_t STATE_PENALIZED_EXACT_COUNT = 4;
constexpr int32_t STATE_BLOCKED_EXACT_COUNT = 5;

// Denominator guards that mirror the Python `max(..., 1)` /
// `max(..., 1e-9)` patterns in anchor_diversity.py. Pulled out as
// named constants so the magic-number detector stays quiet and so
// the parity with Python is explicit line-by-line.
constexpr int32_t MIN_COUNT_DENOMINATOR = 1;
constexpr double SHARE_DENOMINATOR_EPSILON = 1e-9;
constexpr double SHARE_WEIGHT = 0.8;
constexpr double COUNT_WEIGHT = 0.2;
constexpr double NEUTRAL_SCORE = 0.5;
constexpr double SPAM_RISK_CEILING = 1.0;
constexpr double SCORE_SLOPE = 0.5;
} // namespace

void evaluate_anchor_diversity_core(
    const int32_t *active_anchor_counts,
    const int32_t *exact_match_counts_before, std::size_t count,
    int32_t min_history_count, double max_exact_match_share,
    int32_t max_exact_match_count, bool hard_cap_enabled,
    int32_t *out_projected_exact_count, double *out_projected_exact_share,
    double *out_share_overflow, double *out_count_overflow_norm,
    double *out_spam_risk, double *out_score_anchor_diversity,
    int32_t *out_state_index, uint8_t *out_would_block) {
  for (std::size_t i = 0; i < count; ++i) {
    const int32_t active = active_anchor_counts[i];
    const int32_t before = exact_match_counts_before[i];

    // PARITY: matches anchor_diversity.py line 127 — active_anchor_count < min
    if (active < min_history_count) {
      out_projected_exact_count[i] = before;
      out_projected_exact_share[i] = 0.0;
      out_share_overflow[i] = 0.0;
      out_count_overflow_norm[i] = 0.0;
      out_spam_risk[i] = 0.0;
      out_score_anchor_diversity[i] = NEUTRAL_SCORE;
      out_state_index[i] = STATE_NEUTRAL_NO_HISTORY;
      out_would_block[i] = 0;
      continue;
    }

    // PARITY: matches anchor_diversity.py line 137 —
    // projected_exact_match_count
    const int32_t projected_count = before + 1;

    // PARITY: matches anchor_diversity.py lines 138-141 — projected_exact_share
    const int32_t denom_count =
        std::max<int32_t>(active + 1, MIN_COUNT_DENOMINATOR);
    const double projected_share =
        static_cast<double>(projected_count) / static_cast<double>(denom_count);

    // PARITY: matches anchor_diversity.py lines 142-145 — share_overflow
    const double share_denominator =
        std::max(1.0 - max_exact_match_share, SHARE_DENOMINATOR_EPSILON);
    const double share_overflow =
        std::max(0.0, projected_share - max_exact_match_share) /
        share_denominator;

    // PARITY: matches anchor_diversity.py lines 146-149 — count_overflow
    const int32_t count_overflow_abs =
        std::max<int32_t>(0, projected_count - max_exact_match_count);
    // PARITY: matches anchor_diversity.py lines 150-153 — count_overflow_norm
    const int32_t count_denom =
        std::max<int32_t>(max_exact_match_count, MIN_COUNT_DENOMINATOR);
    const double count_overflow_norm =
        std::min(SPAM_RISK_CEILING, static_cast<double>(count_overflow_abs) /
                                        static_cast<double>(count_denom));

    // PARITY: matches anchor_diversity.py line 154 — spam_risk
    const double spam_risk =
        std::min(SPAM_RISK_CEILING, (SHARE_WEIGHT * share_overflow) +
                                        (COUNT_WEIGHT * count_overflow_norm));
    // PARITY: matches anchor_diversity.py line 156 — score_anchor_diversity
    const double score = NEUTRAL_SCORE - (SCORE_SLOPE * spam_risk);
    // PARITY: matches anchor_diversity.py lines 158-160 — blocked decision
    const bool blocked =
        hard_cap_enabled && (projected_count > max_exact_match_count);

    // PARITY: matches anchor_diversity.py lines 162-169 — state selection
    int32_t state;
    if (blocked) {
      state = STATE_BLOCKED_EXACT_COUNT;
    } else if (count_overflow_abs > 0) {
      state = STATE_PENALIZED_EXACT_COUNT;
    } else if (share_overflow > 0.0) {
      state = STATE_PENALIZED_EXACT_SHARE;
    } else {
      state = STATE_NEUTRAL_BELOW_THRESHOLD;
    }

    out_projected_exact_count[i] = projected_count;
    out_projected_exact_share[i] = projected_share;
    out_share_overflow[i] = share_overflow;
    out_count_overflow_norm[i] = count_overflow_norm;
    out_spam_risk[i] = spam_risk;
    out_score_anchor_diversity[i] = score;
    out_state_index[i] = state;
    out_would_block[i] = blocked ? 1 : 0;
  }
}

#ifndef XF_BENCH_MODE
// pybind11 boundary — pins the C++ computation behind a batched call so
// the ranker can amortise the GIL handoff across many candidates in a
// single invocation. Inputs are parallel NumPy arrays; output is a
// Python dict of parallel NumPy arrays keyed by field name.
py::dict
evaluate_batch(py::array_t<int32_t, py::array::c_style | py::array::forcecast>
                   active_anchor_counts,
               py::array_t<int32_t, py::array::c_style | py::array::forcecast>
                   exact_match_counts_before,
               int32_t min_history_count, double max_exact_match_share,
               int32_t max_exact_match_count, bool hard_cap_enabled) {
  auto active_buf = active_anchor_counts.request();
  auto before_buf = exact_match_counts_before.request();

  if (active_buf.ndim != 1 || before_buf.ndim != 1) {
    throw std::runtime_error(
        "active_anchor_counts and exact_match_counts_before must be 1-D int32 "
        "arrays");
  }
  if (active_buf.shape[0] != before_buf.shape[0]) {
    throw std::runtime_error(
        "active_anchor_counts and exact_match_counts_before must be the same "
        "length");
  }

  const auto count = static_cast<std::size_t>(active_buf.shape[0]);

  auto projected_count = py::array_t<int32_t>(count);
  auto projected_share = py::array_t<double>(count);
  auto share_overflow = py::array_t<double>(count);
  auto count_overflow_norm = py::array_t<double>(count);
  auto spam_risk = py::array_t<double>(count);
  auto score_out = py::array_t<double>(count);
  auto state_index = py::array_t<int32_t>(count);
  auto would_block = py::array_t<uint8_t>(count);

  // Resolve every output buffer_info BEFORE releasing the GIL — request()
  // is a Python API call and must not run without the GIL. Each stored
  // buffer_info keeps its pointer alive for the core call.
  auto projected_count_buf = projected_count.request();
  auto projected_share_buf = projected_share.request();
  auto share_overflow_buf = share_overflow.request();
  auto count_overflow_norm_buf = count_overflow_norm.request();
  auto spam_risk_buf = spam_risk.request();
  auto score_out_buf = score_out.request();
  auto state_index_buf = state_index.request();
  auto would_block_buf = would_block.request();

  {
    py::gil_scoped_release release;
    evaluate_anchor_diversity_core(
        static_cast<const int32_t *>(active_buf.ptr),
        static_cast<const int32_t *>(before_buf.ptr), count, min_history_count,
        max_exact_match_share, max_exact_match_count, hard_cap_enabled,
        static_cast<int32_t *>(projected_count_buf.ptr),
        static_cast<double *>(projected_share_buf.ptr),
        static_cast<double *>(share_overflow_buf.ptr),
        static_cast<double *>(count_overflow_norm_buf.ptr),
        static_cast<double *>(spam_risk_buf.ptr),
        static_cast<double *>(score_out_buf.ptr),
        static_cast<int32_t *>(state_index_buf.ptr),
        static_cast<uint8_t *>(would_block_buf.ptr));
  }

  py::dict result;
  result["projected_exact_count"] = projected_count;
  result["projected_exact_share"] = projected_share;
  result["share_overflow"] = share_overflow;
  result["count_overflow_norm"] = count_overflow_norm;
  result["spam_risk"] = spam_risk;
  result["score_anchor_diversity"] = score_out;
  result["state_index"] = state_index;
  result["would_block"] = would_block;
  return result;
}

PYBIND11_MODULE(anchor_diversity, m) {
  m.doc() =
      "FR-045 anchor diversity / exact-match reuse guard — C++ batch fast "
      "path.\n"
      "Mirrors the Python reference at "
      "backend/apps/pipeline/services/anchor_diversity.py at 1e-6 parity. "
      "Python owns normalization (Unicode \\w regex) and diagnostics-dict "
      "composition; C++ only handles the arithmetic inner loop.";

  m.def("evaluate_batch", &evaluate_batch, py::arg("active_anchor_counts"),
        py::arg("exact_match_counts_before"), py::arg("min_history_count"),
        py::arg("max_exact_match_share"), py::arg("max_exact_match_count"),
        py::arg("hard_cap_enabled"),
        "Batch FR-045 anchor diversity scorer. Inputs are parallel int32 "
        "arrays of length N; returns a dict of parallel arrays (projected_"
        "exact_count, projected_exact_share, share_overflow, count_overflow_"
        "norm, spam_risk, score_anchor_diversity, state_index, would_block). "
        "State-index encoding: 1=neutral_no_history, 2=neutral_below_"
        "threshold, 3=penalized_exact_share, 4=penalized_exact_count, "
        "5=blocked_exact_count. (States 0=disabled and 6=neutral_no_anchor "
        "are handled by the Python caller before delegation.)");
}
#endif
