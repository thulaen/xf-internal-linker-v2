//! Feature normalization and missing-value handling.

use crate::ranking_schema::{CandidateInput, FeatureVector};

pub const NEUTRAL_SCORE: f32 = 0.5;

#[derive(Clone, Debug)]
pub struct NormalizedCandidate {
    pub candidate_id: String,
    pub destination_id: String,
    pub features: FeatureVector,
    pub notes: Vec<String>,
}

pub fn normalize_candidate(candidate: CandidateInput) -> NormalizedCandidate {
    let mut notes = Vec::new();
    let features = FeatureVector::new(
        normalize_value("semantic", candidate.features.semantic, &mut notes),
        normalize_value("keyword", candidate.features.keyword, &mut notes),
        normalize_value("node", candidate.features.node, &mut notes),
        normalize_value("quality", candidate.features.quality, &mut notes),
    );
    NormalizedCandidate {
        candidate_id: candidate.candidate_id,
        destination_id: candidate.destination_id,
        features,
        notes,
    }
}

fn normalize_value(name: &str, value: f32, notes: &mut Vec<String>) -> f32 {
    if !value.is_finite() {
        notes.push(format!(
            "{name} used neutral because the input was not finite"
        ));
        return NEUTRAL_SCORE;
    }
    if value < 0.0 {
        notes.push(format!("{name} clamped to 0.0"));
        return 0.0;
    }
    if value > 1.0 {
        notes.push(format!("{name} clamped to 1.0"));
        return 1.0;
    }
    value
}
