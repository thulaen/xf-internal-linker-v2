//! Rust authority crate for bounded ranking decisions.

mod ranking_core;
mod ranking_explain;
mod ranking_features;
mod ranking_governance;
mod ranking_memory;
mod ranking_profiles;
mod ranking_schema;

#[cfg(test)]
mod wolfram_oracle;

use pyo3::prelude::*;

pub use ranking_core::rank_candidates;
pub use ranking_explain::explain;
pub use ranking_governance::validate_profile;
pub use ranking_memory::memory_estimate;
use ranking_memory::memory_estimate_py;
pub use ranking_schema::{
    CandidateInput, Contribution, FeatureVector, GovernanceVerdict, MemoryBudget, MemoryEstimate,
    MemoryEstimateRequest, ProfileValidationRequest, RankedBatch, RankingPolicy, RankingRequest,
    ScoredCandidate, WeightProfile,
};

#[pyfunction(name = "rank_candidates")]
#[allow(clippy::needless_pass_by_value)]
fn rank_candidates_py(request: PyRef<'_, RankingRequest>) -> PyResult<RankedBatch> {
    rank_candidates(
        request.candidates.clone(),
        &request.profile,
        &request.policy,
    )
}

#[pyfunction(name = "validate_profile")]
#[allow(clippy::needless_pass_by_value)]
fn validate_profile_py(request: PyRef<'_, ProfileValidationRequest>) -> GovernanceVerdict {
    validate_profile(&request.candidate, &request.baseline, request.max_movement)
}

#[pyfunction(name = "explain")]
#[allow(clippy::needless_pass_by_value)]
fn explain_py(decision_id: &str) -> Option<String> {
    explain(decision_id)
}

#[pymodule]
fn ranking_decision_engine(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_class::<CandidateInput>()?;
    m.add_class::<Contribution>()?;
    m.add_class::<FeatureVector>()?;
    m.add_class::<GovernanceVerdict>()?;
    m.add_class::<MemoryBudget>()?;
    m.add_class::<MemoryEstimate>()?;
    m.add_class::<MemoryEstimateRequest>()?;
    m.add_class::<ProfileValidationRequest>()?;
    m.add_class::<RankedBatch>()?;
    m.add_class::<RankingPolicy>()?;
    m.add_class::<RankingRequest>()?;
    m.add_class::<ScoredCandidate>()?;
    m.add_class::<WeightProfile>()?;
    m.add_function(wrap_pyfunction!(rank_candidates_py, m)?)?;
    m.add_function(wrap_pyfunction!(memory_estimate_py, m)?)?;
    m.add_function(wrap_pyfunction!(validate_profile_py, m)?)?;
    m.add_function(wrap_pyfunction!(explain_py, m)?)?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::{
        explain, memory_estimate, rank_candidates, validate_profile, CandidateInput, FeatureVector,
        MemoryBudget, RankingPolicy, WeightProfile,
    };

    fn profile() -> WeightProfile {
        WeightProfile::new("recommended".to_string(), 0.4, 0.25, 0.2, 0.15)
    }

    fn candidate(id: &str, destination: &str, semantic: f32) -> CandidateInput {
        CandidateInput::new(
            id.to_string(),
            destination.to_string(),
            "host".to_string(),
            FeatureVector::new(semantic, 0.5, 0.5, 0.5),
        )
    }

    #[test]
    fn memory_estimate_blocks_oversized_requests() {
        let estimate = memory_estimate(100_000_000, 2 * 1024 * 1024 * 1024);
        assert!(!estimate.allowed);
        assert_eq!(estimate.reason, "split batch required");
    }

    #[test]
    fn rank_candidates_orders_by_score_and_deduplicates_destination() {
        let policy = RankingPolicy::new(2, MemoryBudget::default_2gb());
        let active_profile = profile();
        let ranked = rank_candidates(
            vec![
                candidate("low", "same-dest", 0.1),
                candidate("high", "same-dest", 0.9),
                candidate("mid", "other-dest", 0.5),
            ],
            &active_profile,
            &policy,
        )
        .expect("ranking should succeed");

        assert_eq!(ranked.status, "ready");
        assert_eq!(ranked.candidates.len(), 2);
        assert_eq!(ranked.candidates[0].candidate_id, "high");
        assert_eq!(ranked.candidates[1].candidate_id, "mid");
    }

    #[test]
    fn invalid_feature_normalizes_to_neutral_and_explains_it() {
        let policy = RankingPolicy::new(1, MemoryBudget::default_2gb());
        let active_profile = profile();
        let ranked = rank_candidates(
            vec![CandidateInput::new(
                "bad".to_string(),
                "dest".to_string(),
                "host".to_string(),
                FeatureVector::new(f32::NAN, 1.0, 1.0, 1.0),
            )],
            &active_profile,
            &policy,
        )
        .expect("ranking should succeed");

        assert!((ranked.candidates[0].score_semantic - 0.5).abs() < f32::EPSILON);
        assert!(ranked.candidates[0]
            .explanation
            .contains("semantic used neutral"));
    }

    #[test]
    fn validate_profile_blocks_zero_weight_and_large_movement() {
        let baseline = profile();
        let zero = WeightProfile::new("bad".to_string(), 0.0, 0.25, 0.2, 0.55);
        let zero_verdict = validate_profile(&zero, &baseline, 0.05);
        assert_eq!(zero_verdict.verdict, "blocked");
        assert_eq!(zero_verdict.reason_code, "weight_below_floor");

        let moved = WeightProfile::new("moved".to_string(), 0.7, 0.1, 0.1, 0.1);
        let moved_verdict = validate_profile(&moved, &baseline, 0.05);
        assert_eq!(moved_verdict.verdict, "blocked");
        assert_eq!(moved_verdict.reason_code, "movement_too_large");
    }

    #[test]
    fn explain_returns_matching_decision_text() {
        let policy = RankingPolicy::new(1, MemoryBudget::default_2gb());
        let active_profile = profile();
        let ranked = rank_candidates(
            vec![candidate("one", "dest", 0.7)],
            &active_profile,
            &policy,
        )
        .expect("ranking should succeed");
        let decision_id = ranked.candidates[0].decision_id.clone();

        let explanation = explain(&decision_id).expect("explanation exists");

        assert!(explanation.contains("candidate one"));
        assert!(explanation.contains("final score"));
    }

    #[test]
    fn wolfram_oracle_marker_stays_test_only() {
        assert_eq!(super::wolfram_oracle::ORACLE_ROLE, "offline-test-only");
    }
}
