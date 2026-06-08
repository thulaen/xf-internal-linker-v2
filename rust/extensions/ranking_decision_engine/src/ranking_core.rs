//! Bounded scoring and deterministic ordering for ranking candidates.

use std::cmp::Ordering;
use std::collections::HashMap;

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;

use crate::ranking_explain::{clear_explanations, remember_explanations};
use crate::ranking_features::{normalize_candidate, NormalizedCandidate};
use crate::ranking_memory::memory_estimate;
use crate::ranking_profiles::validate_profile_for_scoring;
use crate::ranking_schema::{
    CandidateInput, Contribution, RankedBatch, RankingPolicy, ScoredCandidate, WeightProfile,
    ENGINE_VERSION,
};

/// Score, deduplicate, and rank candidates under a validated profile and memory
/// budget.
///
/// # Errors
///
/// Returns a Python `ValueError` only when contribution math produces a
/// non-finite final score after profile validation. Oversized requests and
/// invalid profiles return a blocked `RankedBatch` instead of raising.
pub fn rank_candidates(
    candidates: Vec<CandidateInput>,
    profile: &WeightProfile,
    policy: &RankingPolicy,
) -> PyResult<RankedBatch> {
    let estimate = memory_estimate(candidates.len(), policy.memory_budget.max_bytes);
    if !estimate.allowed {
        clear_explanations();
        return Ok(RankedBatch::blocked(
            &estimate.reason,
            estimate.estimated_bytes,
        ));
    }
    if let Some(reason) = validate_profile_for_scoring(profile) {
        clear_explanations();
        return Ok(RankedBatch::blocked(&reason, estimate.estimated_bytes));
    }
    if policy.top_n == 0 {
        clear_explanations();
        return Ok(RankedBatch::ready(Vec::new(), estimate.estimated_bytes));
    }

    let scored = score_and_deduplicate(candidates, profile)?;
    let top_candidates = top_n(scored, policy.top_n);
    remember_explanations(&top_candidates);
    Ok(RankedBatch::ready(top_candidates, estimate.estimated_bytes))
}

fn score_and_deduplicate(
    candidates: Vec<CandidateInput>,
    profile: &WeightProfile,
) -> PyResult<Vec<ScoredCandidate>> {
    let mut by_destination: HashMap<String, ScoredCandidate> = HashMap::new();
    for candidate in candidates {
        let normalized = normalize_candidate(candidate);
        let scored = score_candidate(&normalized, profile)?;
        by_destination
            .entry(scored.destination_id.clone())
            .and_modify(|current| replace_if_better(current, &scored))
            .or_insert(scored);
    }
    Ok(by_destination.into_values().collect())
}

fn replace_if_better(current: &mut ScoredCandidate, scored: &ScoredCandidate) {
    let score_order = scored.score_final.total_cmp(&current.score_final);
    let better_score = score_order == Ordering::Greater;
    let stable_tie = score_order == Ordering::Equal && scored.candidate_id < current.candidate_id;
    if better_score || stable_tie {
        *current = scored.clone();
    }
}

fn top_n(mut scored: Vec<ScoredCandidate>, limit: usize) -> Vec<ScoredCandidate> {
    scored.sort_by(compare_scored);
    scored.truncate(limit);
    scored
}

fn compare_scored(left: &ScoredCandidate, right: &ScoredCandidate) -> Ordering {
    right
        .score_final
        .total_cmp(&left.score_final)
        .then_with(|| left.candidate_id.cmp(&right.candidate_id))
}

fn score_candidate(
    candidate: &NormalizedCandidate,
    profile: &WeightProfile,
) -> PyResult<ScoredCandidate> {
    let contributions = contributions(candidate, profile);
    let score_final = final_score(&contributions)?;
    Ok(ScoredCandidate {
        candidate_id: candidate.candidate_id.clone(),
        destination_id: candidate.destination_id.clone(),
        decision_id: decision_id(profile, &candidate.candidate_id),
        score_semantic: candidate.features.semantic,
        score_keyword: candidate.features.keyword,
        score_node: candidate.features.node,
        score_quality: candidate.features.quality,
        score_final,
        explanation: explanation(candidate, &contributions, score_final),
        contributions,
        engine_version: ENGINE_VERSION.to_string(),
    })
}

fn contributions(candidate: &NormalizedCandidate, profile: &WeightProfile) -> Vec<Contribution> {
    vec![
        Contribution::new("semantic", candidate.features.semantic * profile.w_semantic),
        Contribution::new("keyword", candidate.features.keyword * profile.w_keyword),
        Contribution::new("node", candidate.features.node * profile.w_node),
        Contribution::new("quality", candidate.features.quality * profile.w_quality),
    ]
}

fn final_score(contributions: &[Contribution]) -> PyResult<f32> {
    let score = contributions.iter().map(|item| item.value).sum::<f32>();
    if !score.is_finite() {
        return Err(PyValueError::new_err("final score was not finite"));
    }
    Ok(score.clamp(0.0, 1.0))
}

fn decision_id(profile: &WeightProfile, candidate_id: &str) -> String {
    format!("rde:{}:{candidate_id}", profile.version)
}

fn explanation(
    candidate: &NormalizedCandidate,
    contributions: &[Contribution],
    score_final: f32,
) -> String {
    let parts = contributions
        .iter()
        .map(|item| format!("{} contribution {:.4}", item.name, item.value))
        .collect::<Vec<_>>()
        .join("; ");
    let notes = if candidate.notes.is_empty() {
        "no neutral fallback used".to_string()
    } else {
        candidate.notes.join("; ")
    };
    format!(
        "candidate {} final score {:.4}; {}; {}",
        candidate.candidate_id, score_final, parts, notes
    )
}
