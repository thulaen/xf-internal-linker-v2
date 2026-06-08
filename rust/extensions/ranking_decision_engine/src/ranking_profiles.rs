//! Ranking profile safety checks.

use crate::ranking_schema::{GovernanceVerdict, WeightProfile};

const MIN_WEIGHT: f32 = 0.01;
const SUM_TOLERANCE: f32 = 0.001;

pub fn validate_profile_inner(
    candidate: &WeightProfile,
    baseline: &WeightProfile,
    max_movement: f32,
) -> GovernanceVerdict {
    if let Some((name, _)) = candidate
        .values()
        .iter()
        .find(|(_, value)| !value.is_finite() || *value < MIN_WEIGHT)
    {
        return GovernanceVerdict::new(
            "blocked",
            "weight_below_floor",
            &format!("{name} weight is below the allowed floor of 0.01."),
        );
    }

    if (candidate.sum() - 1.0).abs() > SUM_TOLERANCE {
        return GovernanceVerdict::new(
            "blocked",
            "weight_sum_invalid",
            "The profile weights must add up to 1.0 within tolerance.",
        );
    }

    movement_verdict(candidate, baseline, max_movement)
}

fn movement_verdict(
    candidate: &WeightProfile,
    baseline: &WeightProfile,
    max_movement: f32,
) -> GovernanceVerdict {
    for ((name, value), (_, base)) in candidate.values().iter().zip(baseline.values()) {
        if (*value - base).abs() > max_movement {
            return GovernanceVerdict::new(
                "blocked",
                "movement_too_large",
                &format!("{name} moved farther than the allowed profile budget."),
            );
        }
    }
    GovernanceVerdict::new(
        "approved",
        "profile_valid",
        "The ranking profile passed Rust validation.",
    )
}

pub fn validate_profile_for_scoring(profile: &WeightProfile) -> Option<String> {
    if profile
        .values()
        .iter()
        .any(|(_, value)| !value.is_finite() || *value < MIN_WEIGHT)
    {
        return Some("weight_below_floor".to_string());
    }
    if (profile.sum() - 1.0).abs() > SUM_TOLERANCE {
        return Some("weight_sum_invalid".to_string());
    }
    None
}
