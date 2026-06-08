//! `xftool ranking <verb-noun>` — ranking-run validity tools.
//!
//! NOTE: Wave 0 is standalone over JSON files. When the §G ranking crates
//! (`ranking_core`, `ranking_profiles`, …) land, the diff logic here will be
//! refactored to reuse them rather than re-parse the run JSON (DRY, ADR 0008 §2).

use std::path::PathBuf;

use clap::Subcommand;

use crate::output::{ExitCode, ToolReport};
use crate::util::{read_json, ToolError};

#[derive(Subcommand, Debug)]
pub enum RankingCmd {
    /// Diff two ranking-run JSONs: added, removed, moved items and rank deltas.
    Diff {
        /// First (baseline) ranking-run JSON.
        a: PathBuf,
        /// Second (candidate) ranking-run JSON.
        b: PathBuf,
    },
}

impl RankingCmd {
    /// Run the selected ranking subcommand.
    ///
    /// # Errors
    /// Returns [`ToolError`] when a file cannot be read or is not a valid run JSON.
    pub fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::Diff { a, b } => {
                let ranks_a = parse_run(&read_json(a)?, &a.display().to_string())?;
                let ranks_b = parse_run(&read_json(b)?, &b.display().to_string())?;
                Ok(diff_runs(&ranks_a, &ranks_b))
            }
        }
    }
}

/// `(id, rank)` pairs for one ranking run, rank starting at 0 = top.
type Ranks = Vec<(String, usize)>;

/// Parse a ranking-run JSON into an ordered `(id, rank)` list.
///
/// Accepted shapes: a top-level array of items, or an object with an `items`
/// array. Each item is either a bare string id or an object with an `id`
/// (or `item_id`) field. Rank is the position in the array.
fn parse_run(value: &serde_json::Value, what: &str) -> Result<Ranks, ToolError> {
    let items = value
        .as_array()
        .or_else(|| value.get("items").and_then(|i| i.as_array()))
        .ok_or_else(|| {
            ToolError::usage(format!(
                "'{what}' must be a JSON array or an object with an 'items' array"
            ))
        })?;

    let mut ranks = Vec::with_capacity(items.len());
    for (rank, item) in items.iter().enumerate() {
        let id = item_id(item).ok_or_else(|| {
            ToolError::usage(format!("'{what}' item at position {rank} has no id"))
        })?;
        ranks.push((id, rank));
    }
    Ok(ranks)
}

/// Extract an item's id from a string item or an object with `id` / `item_id`.
fn item_id(item: &serde_json::Value) -> Option<String> {
    if let Some(s) = item.as_str() {
        return Some(s.to_string());
    }
    item.get("id")
        .or_else(|| item.get("item_id"))
        .and_then(|v| v.as_str())
        .map(str::to_string)
}

/// Compare two runs and build the diff report. Exit code is `Findings` when the
/// two runs are not identical, `Ok` when they match exactly.
fn diff_runs(a: &Ranks, b: &Ranks) -> ToolReport {
    let lookup_a: std::collections::HashMap<&str, usize> =
        a.iter().map(|(id, r)| (id.as_str(), *r)).collect();
    let lookup_b: std::collections::HashMap<&str, usize> =
        b.iter().map(|(id, r)| (id.as_str(), *r)).collect();

    let mut added: Vec<&str> = b
        .iter()
        .filter(|(id, _)| !lookup_a.contains_key(id.as_str()))
        .map(|(id, _)| id.as_str())
        .collect();
    let mut removed: Vec<&str> = a
        .iter()
        .filter(|(id, _)| !lookup_b.contains_key(id.as_str()))
        .map(|(id, _)| id.as_str())
        .collect();
    added.sort_unstable();
    removed.sort_unstable();

    // Moved: present in both, different rank. Report id and signed delta.
    let mut moved: Vec<(String, i64)> = Vec::new();
    for (id, ra) in a {
        if let Some(rb) = lookup_b.get(id.as_str()) {
            #[allow(clippy::cast_possible_wrap)]
            let delta = *rb as i64 - *ra as i64;
            if delta != 0 {
                moved.push((id.clone(), delta));
            }
        }
    }
    moved.sort_by(|x, y| y.1.abs().cmp(&x.1.abs()).then_with(|| x.0.cmp(&y.0)));

    let changed = !added.is_empty() || !removed.is_empty() || !moved.is_empty();
    let exit = if changed {
        ExitCode::Findings
    } else {
        ExitCode::Ok
    };
    let summary = format!(
        "ranking diff: {} added, {} removed, {} moved",
        added.len(),
        removed.len(),
        moved.len()
    );

    let mut report = ToolReport::new(summary, exit)
        .row("added", join_or_none(&added))
        .row("removed", join_or_none(&removed));
    for (id, delta) in &moved {
        let dir = if *delta > 0 { "down" } else { "up" };
        report = report.row(
            format!("moved:{id}"),
            format!("{} by {} ({dir})", signed(*delta), delta.abs()),
        );
    }
    report
}

fn join_or_none(items: &[&str]) -> String {
    if items.is_empty() {
        "(none)".to_string()
    } else {
        items.join(", ")
    }
}

fn signed(d: i64) -> String {
    if d > 0 {
        format!("+{d}")
    } else {
        d.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn ranks(ids: &[&str]) -> Ranks {
        ids.iter()
            .enumerate()
            .map(|(r, id)| ((*id).to_string(), r))
            .collect()
    }

    #[test]
    fn identical_runs_report_ok_and_no_changes() {
        let r = diff_runs(&ranks(&["a", "b", "c"]), &ranks(&["a", "b", "c"]));
        assert_eq!(r.exit, ExitCode::Ok);
        assert!(r.summary.contains("0 added, 0 removed, 0 moved"));
    }

    #[test]
    fn detects_added_and_removed() {
        let r = diff_runs(&ranks(&["a", "b"]), &ranks(&["b", "c"]));
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.summary.contains("1 added"));
        assert!(r.summary.contains("1 removed"));
    }

    #[test]
    fn detects_moved_with_signed_delta() {
        // "b" goes from rank 1 to rank 0 -> moved up by 1 (delta -1).
        let r = diff_runs(&ranks(&["a", "b"]), &ranks(&["b", "a"]));
        assert_eq!(r.exit, ExitCode::Findings);
        let moved_row = r
            .rows
            .iter()
            .find(|(k, _)| k.starts_with("moved:b"))
            .unwrap();
        assert!(moved_row.1.contains("up"));
    }

    #[test]
    fn parse_run_accepts_array_of_strings() {
        let ranks = parse_run(&json!(["x", "y"]), "t").unwrap();
        assert_eq!(ranks, vec![("x".to_string(), 0), ("y".to_string(), 1)]);
    }

    #[test]
    fn parse_run_accepts_items_objects() {
        let v = json!({"items": [{"id": "x"}, {"item_id": "y"}]});
        let ranks = parse_run(&v, "t").unwrap();
        assert_eq!(ranks, vec![("x".to_string(), 0), ("y".to_string(), 1)]);
    }

    #[test]
    fn parse_run_rejects_non_array() {
        assert!(parse_run(&json!({"nope": 1}), "t").is_err());
    }

    #[test]
    fn parse_run_rejects_item_without_id() {
        assert!(parse_run(&json!([{"score": 1}]), "t").is_err());
    }
}
