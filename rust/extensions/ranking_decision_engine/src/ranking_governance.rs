//! Governance verdicts for ranking profile changes.

use crate::ranking_profiles::validate_profile_inner;
use crate::ranking_schema::{GovernanceVerdict, WeightProfile};

#[must_use]
pub fn validate_profile(
    candidate: &WeightProfile,
    baseline: &WeightProfile,
    max_movement: f32,
) -> GovernanceVerdict {
    validate_profile_inner(candidate, baseline, max_movement)
}
