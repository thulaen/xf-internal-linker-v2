//! Memory estimates and the 2 GB runtime budget.

use crate::ranking_schema::{MemoryEstimate, MemoryEstimateRequest};

const FIXED_REQUEST_BYTES: u64 = 4096;
const PER_CANDIDATE_BYTES: u64 = 256;

#[must_use]
pub fn memory_estimate(candidate_count: usize, max_bytes: u64) -> MemoryEstimate {
    let count = u64::try_from(candidate_count).unwrap_or(u64::MAX);
    let variable = count.saturating_mul(PER_CANDIDATE_BYTES);
    let estimated = FIXED_REQUEST_BYTES.saturating_add(variable);
    let allowed = estimated <= max_bytes;
    MemoryEstimate {
        allowed,
        estimated_bytes: estimated,
        max_bytes,
        reason: reason_for(allowed),
    }
}

#[pyo3::pyfunction(name = "memory_estimate")]
#[must_use]
#[allow(clippy::needless_pass_by_value)]
pub fn memory_estimate_py(request: MemoryEstimateRequest) -> MemoryEstimate {
    memory_estimate(request.candidate_count, request.memory_budget.max_bytes)
}

fn reason_for(allowed: bool) -> String {
    if allowed {
        "within budget".to_string()
    } else {
        "split batch required".to_string()
    }
}
