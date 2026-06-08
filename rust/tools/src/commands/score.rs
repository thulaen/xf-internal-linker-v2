//! `xftool score <verb-noun>` — score-breakdown validity tools.
//!
//! NOTE: Wave 0 validates a standalone breakdown JSON. When the §G ranking
//! crates land, the bounds/sum rules will be sourced from the canonical score
//! definition instead of being re-declared in the JSON (DRY, ADR 0008 §2).

use std::path::PathBuf;

use clap::Subcommand;

use crate::output::{ExitCode, ToolReport};
use crate::util::{read_json, ToolError};

/// Default allowed gap between the component sum and the declared total.
const DEFAULT_TOLERANCE: f64 = 1e-6;

#[derive(Subcommand, Debug)]
pub enum ScoreCmd {
    /// Assert components sum to total within tolerance, are finite, and are in bounds.
    ValidateBreakdown {
        /// Score-breakdown JSON: `{ "total": N, "components": {name: value}, "bounds"?: {name: [lo, hi]} }`.
        breakdown: PathBuf,
        /// Allowed absolute gap between component sum and total.
        #[arg(long, default_value_t = DEFAULT_TOLERANCE)]
        tolerance: f64,
    },
}

impl ScoreCmd {
    /// Run the selected score subcommand.
    ///
    /// # Errors
    /// Returns [`ToolError`] when the file cannot be read or is not a valid breakdown.
    pub fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::ValidateBreakdown {
                breakdown,
                tolerance,
            } => {
                let value = read_json(breakdown)?;
                let parsed = parse_breakdown(&value)?;
                Ok(validate_breakdown(&parsed, *tolerance))
            }
        }
    }
}

/// A parsed breakdown: the declared total, named components, and optional bounds.
struct Breakdown {
    total: f64,
    components: Vec<(String, f64)>,
    bounds: Vec<(String, f64, f64)>,
}

fn parse_breakdown(value: &serde_json::Value) -> Result<Breakdown, ToolError> {
    let total = value
        .get("total")
        .and_then(serde_json::Value::as_f64)
        .ok_or_else(|| ToolError::usage("breakdown needs a numeric 'total' field"))?;

    let comp_obj = value
        .get("components")
        .and_then(|c| c.as_object())
        .ok_or_else(|| ToolError::usage("breakdown needs a 'components' object"))?;

    let mut components = Vec::with_capacity(comp_obj.len());
    for (name, v) in comp_obj {
        let n = v
            .as_f64()
            .ok_or_else(|| ToolError::usage(format!("component '{name}' is not a number")))?;
        components.push((name.clone(), n));
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
    Ok(Breakdown {
        total,
        components,
        bounds,
    })
}

/// Check finiteness, the sum-to-total rule, and bounds. Exit `Findings` on any
/// violation, `Ok` when the breakdown is clean.
fn validate_breakdown(b: &Breakdown, tolerance: f64) -> ToolReport {
    let mut violations: Vec<String> = Vec::new();

    if !b.total.is_finite() {
        violations.push("total is not finite (NaN/inf)".to_string());
    }
    let mut sum = 0.0;
    for (name, v) in &b.components {
        if v.is_finite() {
            sum += *v;
        } else {
            violations.push(format!("component '{name}' is not finite (NaN/inf)"));
        }
    }

    let gap = (sum - b.total).abs();
    if b.total.is_finite() && gap > tolerance {
        violations.push(format!(
            "components sum to {sum} but total is {} (gap {gap} > tolerance {tolerance})",
            b.total
        ));
    }

    let comp_lookup: std::collections::HashMap<&str, f64> =
        b.components.iter().map(|(n, v)| (n.as_str(), *v)).collect();
    for (name, lo, hi) in &b.bounds {
        match comp_lookup.get(name.as_str()) {
            Some(&v) if v.is_finite() && (v < *lo || v > *hi) => {
                violations.push(format!(
                    "component '{name}' = {v} is outside bounds [{lo}, {hi}]"
                ));
            }
            None => violations.push(format!("bounds declared for unknown component '{name}'")),
            _ => {}
        }
    }

    let exit = if violations.is_empty() {
        ExitCode::Ok
    } else {
        ExitCode::Findings
    };
    let summary = if violations.is_empty() {
        format!(
            "score breakdown valid: {} components sum to total within {tolerance}",
            b.components.len()
        )
    } else {
        format!("score breakdown invalid: {} violation(s)", violations.len())
    };
    let mut report = ToolReport::new(summary, exit)
        .row("total", b.total.to_string())
        .row("component_sum", sum.to_string());
    for (i, v) in violations.iter().enumerate() {
        report = report.row(format!("violation_{}", i + 1), v.clone());
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn bd(total: f64, comps: &[(&str, f64)]) -> Breakdown {
        Breakdown {
            total,
            components: comps.iter().map(|(n, v)| ((*n).to_string(), *v)).collect(),
            bounds: Vec::new(),
        }
    }

    #[test]
    fn valid_breakdown_passes() {
        let r = validate_breakdown(&bd(1.0, &[("a", 0.6), ("b", 0.4)]), DEFAULT_TOLERANCE);
        assert_eq!(r.exit, ExitCode::Ok);
    }

    #[test]
    fn sum_mismatch_is_a_violation() {
        let r = validate_breakdown(&bd(1.0, &[("a", 0.6), ("b", 0.1)]), DEFAULT_TOLERANCE);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.summary.contains("invalid"));
    }

    #[test]
    fn nan_component_is_flagged() {
        let r = validate_breakdown(&bd(1.0, &[("a", f64::NAN)]), DEFAULT_TOLERANCE);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("not finite")));
    }

    #[test]
    fn out_of_bounds_component_is_flagged() {
        let mut b = bd(0.5, &[("a", 0.5)]);
        b.bounds.push(("a".to_string(), 0.0, 0.4));
        let r = validate_breakdown(&b, DEFAULT_TOLERANCE);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("outside bounds")));
    }

    #[test]
    fn parse_rejects_missing_total() {
        assert!(parse_breakdown(&json!({"components": {}})).is_err());
    }

    #[test]
    fn parse_reads_bounds() {
        let v = json!({"total": 1.0, "components": {"a": 1.0}, "bounds": {"a": [0.0, 2.0]}});
        let b = parse_breakdown(&v).unwrap();
        assert_eq!(b.bounds.len(), 1);
    }
}
