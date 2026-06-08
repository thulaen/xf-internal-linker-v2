//! `xftool weights <verb-noun>` — weight-profile lint tools.
//!
//! NOTE: Wave 0 lints a standalone profile JSON. When the §G `ranking_profiles`
//! crate lands, the never-zero / bounds / monotonicity rules will be sourced
//! from the canonical profile schema instead of re-declared here (ADR 0008 §2).

use std::path::PathBuf;

use clap::Subcommand;

use crate::output::{ExitCode, ToolReport};
use crate::util::{read_json, ToolError};

#[derive(Subcommand, Debug)]
pub enum WeightsCmd {
    /// Never-zero, bounds, and monotonicity checks on a weight profile.
    Lint {
        /// Weight-profile JSON: `{ "weights": {name: value}, "bounds"?: {name: [lo, hi]}, "monotonic"?: [name, ...] }`.
        profile: PathBuf,
    },
}

impl WeightsCmd {
    /// Run the selected weights subcommand.
    ///
    /// # Errors
    /// Returns [`ToolError`] when the profile cannot be read or parsed.
    pub fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::Lint { profile } => {
                let value = read_json(profile)?;
                let p = parse_profile(&value)?;
                Ok(lint_profile(&p))
            }
        }
    }
}

/// Parsed weight profile: ordered weights, optional bounds, and the names that
/// must be non-decreasing in declared order.
struct Profile {
    weights: Vec<(String, f64)>,
    bounds: Vec<(String, f64, f64)>,
    monotonic: Vec<String>,
}

fn parse_profile(value: &serde_json::Value) -> Result<Profile, ToolError> {
    let wobj = value
        .get("weights")
        .and_then(|w| w.as_object())
        .ok_or_else(|| ToolError::usage("profile needs a 'weights' object"))?;
    let mut weights = Vec::with_capacity(wobj.len());
    for (name, v) in wobj {
        let n = v
            .as_f64()
            .ok_or_else(|| ToolError::usage(format!("weight '{name}' is not a number")))?;
        weights.push((name.clone(), n));
    }

    let mut bounds = Vec::new();
    if let Some(bobj) = value.get("bounds").and_then(|b| b.as_object()) {
        for (name, pair) in bobj {
            let arr = pair.as_array().filter(|a| a.len() == 2).ok_or_else(|| {
                ToolError::usage(format!("bounds for '{name}' must be a [lo, hi] pair"))
            })?;
            let lo = arr[0].as_f64().ok_or_else(|| {
                ToolError::usage(format!("bounds lo for '{name}' is not a number"))
            })?;
            let hi = arr[1].as_f64().ok_or_else(|| {
                ToolError::usage(format!("bounds hi for '{name}' is not a number"))
            })?;
            bounds.push((name.clone(), lo, hi));
        }
    }

    let monotonic = value
        .get("monotonic")
        .and_then(|m| m.as_array())
        .map(|arr| {
            arr.iter()
                .filter_map(|v| v.as_str().map(str::to_string))
                .collect()
        })
        .unwrap_or_default();

    Ok(Profile {
        weights,
        bounds,
        monotonic,
    })
}

/// Lint a profile. Exit `Findings` on any violation (the DEFAULT-ON never-zero
/// rule, out-of-bounds weights, or a broken monotonic chain).
fn lint_profile(p: &Profile) -> ToolReport {
    let mut violations: Vec<String> = Vec::new();
    let lookup: std::collections::HashMap<&str, f64> =
        p.weights.iter().map(|(n, v)| (n.as_str(), *v)).collect();

    // Never-zero (and never-NaN/inf): every weight must be a finite non-zero value.
    for (name, v) in &p.weights {
        if !v.is_finite() {
            violations.push(format!("weight '{name}' is not finite (NaN/inf)"));
        } else if *v == 0.0 {
            violations.push(format!("weight '{name}' is zero (never-zero rule)"));
        }
    }

    // Bounds.
    for (name, lo, hi) in &p.bounds {
        match lookup.get(name.as_str()) {
            Some(&v) if v.is_finite() && (v < *lo || v > *hi) => {
                violations.push(format!(
                    "weight '{name}' = {v} is outside bounds [{lo}, {hi}]"
                ));
            }
            None => violations.push(format!("bounds declared for unknown weight '{name}'")),
            _ => {}
        }
    }

    // Monotonicity: weights named in `monotonic` order must be non-decreasing.
    let mut prev: Option<(&str, f64)> = None;
    for name in &p.monotonic {
        match lookup.get(name.as_str()) {
            Some(&v) => {
                if let Some((pname, pv)) = prev {
                    if v < pv {
                        violations.push(format!(
                            "monotonicity broken: '{name}' ({v}) < '{pname}' ({pv})"
                        ));
                    }
                }
                prev = Some((name, v));
            }
            None => violations.push(format!("monotonic list names unknown weight '{name}'")),
        }
    }

    let exit = if violations.is_empty() {
        ExitCode::Ok
    } else {
        ExitCode::Findings
    };
    let summary = if violations.is_empty() {
        format!("weights lint ok: {} weight(s) clean", p.weights.len())
    } else {
        format!("weights lint: {} violation(s)", violations.len())
    };
    let mut report =
        ToolReport::new(summary, exit).row("weight_count", p.weights.len().to_string());
    for (i, v) in violations.iter().enumerate() {
        report = report.row(format!("violation_{}", i + 1), v.clone());
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn profile(weights: &[(&str, f64)]) -> Profile {
        Profile {
            weights: weights
                .iter()
                .map(|(n, v)| ((*n).to_string(), *v))
                .collect(),
            bounds: Vec::new(),
            monotonic: Vec::new(),
        }
    }

    #[test]
    fn clean_profile_passes() {
        let r = lint_profile(&profile(&[("a", 0.5), ("b", 1.0)]));
        assert_eq!(r.exit, ExitCode::Ok);
    }

    #[test]
    fn zero_weight_is_violation() {
        let r = lint_profile(&profile(&[("a", 0.0)]));
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("never-zero")));
    }

    #[test]
    fn out_of_bounds_weight_flagged() {
        let mut p = profile(&[("a", 5.0)]);
        p.bounds.push(("a".to_string(), 0.0, 1.0));
        let r = lint_profile(&p);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("outside bounds")));
    }

    #[test]
    fn broken_monotonic_chain_flagged() {
        let mut p = profile(&[("a", 2.0), ("b", 1.0)]);
        p.monotonic = vec!["a".into(), "b".into()];
        let r = lint_profile(&p);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r
            .rows
            .iter()
            .any(|(_, v)| v.contains("monotonicity broken")));
    }

    #[test]
    fn satisfied_monotonic_chain_passes() {
        let mut p = profile(&[("a", 1.0), ("b", 2.0)]);
        p.monotonic = vec!["a".into(), "b".into()];
        assert_eq!(lint_profile(&p).exit, ExitCode::Ok);
    }

    #[test]
    fn parse_requires_weights() {
        assert!(parse_profile(&json!({"bounds": {}})).is_err());
    }

    #[test]
    fn parse_reads_monotonic_list() {
        let p = parse_profile(&json!({"weights": {"a": 1.0}, "monotonic": ["a"]})).unwrap();
        assert_eq!(p.monotonic, vec!["a".to_string()]);
    }
}
