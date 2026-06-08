//! `xftool store <verb-noun>` — compiled-artifact store tools.
//!
//! Reads the content-addressed store manifest produced by
//! `scripts/ensure_compiled_artifacts.py`. The manifest shape is:
//! `{ "store": { "<sha>": { "last_used_at": "...", "bytes": N, ... } },
//!    "active": { "<runtime>": { "artifacts": [ { "sha256": "<sha>" }, ... ] } },
//!    "<runtime>_hash": "<sha>" }`.
//! A store SHA is *referenced* when it appears in any active runtime's
//! `artifacts[].sha256` or as a top-level `*_hash`. Read-only (a report only).

use std::path::PathBuf;

use clap::Subcommand;

use crate::output::{ExitCode, ToolReport};
use crate::util::{read_json, ToolError};

#[derive(Subcommand, Debug)]
pub enum StoreCmd {
    /// Report unreferenced / old SHAs in the compiled-artifacts store (read-only).
    GcReport {
        /// Path to the store `manifest.json`.
        manifest: PathBuf,
        /// Flag store SHAs whose `last_used_at` date is on or before this cutoff
        /// (`YYYY-MM-DD`). Lexicographic compare on ISO-8601 timestamps.
        #[arg(long)]
        older_than: Option<String>,
    },
}

impl StoreCmd {
    /// Run the selected store subcommand.
    ///
    /// # Errors
    /// Returns [`ToolError`] when the manifest cannot be read or parsed.
    pub fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::GcReport {
                manifest,
                older_than,
            } => {
                let value = read_json(manifest)?;
                Ok(gc_report(&value, older_than.as_deref()))
            }
        }
    }
}

/// Collect every SHA referenced by an active runtime or a top-level `*_hash`.
fn referenced_shas(manifest: &serde_json::Value) -> std::collections::HashSet<String> {
    let mut refs = std::collections::HashSet::new();

    if let Some(active) = manifest.get("active").and_then(|a| a.as_object()) {
        for runtime in active.values() {
            if let Some(arts) = runtime.get("artifacts").and_then(|a| a.as_array()) {
                for art in arts {
                    if let Some(sha) = art.get("sha256").and_then(|s| s.as_str()) {
                        refs.insert(sha.to_string());
                    }
                }
            }
        }
    }

    // Top-level "<runtime>_hash" values also pin a store SHA.
    if let Some(obj) = manifest.as_object() {
        for (key, val) in obj {
            if key.ends_with("_hash") {
                if let Some(sha) = val.as_str() {
                    refs.insert(sha.to_string());
                }
            }
        }
    }
    refs
}

/// Build the GC report. Exit `Findings` when any SHA is unreferenced or old,
/// `Ok` when the store is fully referenced and fresh.
fn gc_report(manifest: &serde_json::Value, older_than: Option<&str>) -> ToolReport {
    let refs = referenced_shas(manifest);
    let store = manifest.get("store").and_then(|s| s.as_object());

    let mut unreferenced: Vec<String> = Vec::new();
    let mut old: Vec<String> = Vec::new();
    let mut total = 0usize;

    if let Some(store) = store {
        total = store.len();
        for (sha, entry) in store {
            if !refs.contains(sha) {
                unreferenced.push(short(sha));
            }
            if let (Some(cutoff), Some(used)) = (
                older_than,
                entry.get("last_used_at").and_then(|v| v.as_str()),
            ) {
                // ISO-8601 timestamps sort lexicographically by date prefix.
                if used
                    .get(..cutoff.len())
                    .is_some_and(|prefix| prefix <= cutoff)
                {
                    old.push(short(sha));
                }
            }
        }
    }
    unreferenced.sort_unstable();
    old.sort_unstable();

    let candidate_count = unreferenced.len() + old.len();
    let exit = if candidate_count == 0 {
        ExitCode::Ok
    } else {
        ExitCode::Findings
    };
    let summary = format!(
        "store gc-report: {total} stored, {} unreferenced, {} old (read-only — use the Python pruner to delete)",
        unreferenced.len(),
        old.len()
    );
    ToolReport::new(summary, exit)
        .row("stored_total", total.to_string())
        .row("referenced", refs.len().to_string())
        .row("unreferenced", join_or_none(&unreferenced))
        .row("old", join_or_none(&old))
}

/// First 12 chars of a SHA for compact display.
fn short(sha: &str) -> String {
    sha.chars().take(12).collect()
}

fn join_or_none(items: &[String]) -> String {
    if items.is_empty() {
        "(none)".to_string()
    } else {
        items.join(", ")
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn manifest_with(referenced: &str, unreferenced: &str) -> serde_json::Value {
        json!({
            "store": {
                referenced: {"last_used_at": "2026-06-07T00:00:00Z", "bytes": 10},
                unreferenced: {"last_used_at": "2020-01-01T00:00:00Z", "bytes": 20}
            },
            "active": {
                "cpp_runtime": {"artifacts": [{"sha256": referenced}]}
            }
        })
    }

    #[test]
    fn unreferenced_sha_is_flagged() {
        let m = manifest_with("aaaa", "bbbb");
        let r = gc_report(&m, None);
        assert_eq!(r.exit, ExitCode::Findings);
        let unref = &r.rows.iter().find(|(k, _)| k == "unreferenced").unwrap().1;
        assert!(unref.contains("bbbb"));
        assert!(!unref.contains("aaaa"));
    }

    #[test]
    fn fully_referenced_store_is_ok() {
        let m = json!({
            "store": {"aaaa": {"last_used_at": "2026-06-07T00:00:00Z"}},
            "active": {"r": {"artifacts": [{"sha256": "aaaa"}]}}
        });
        assert_eq!(gc_report(&m, None).exit, ExitCode::Ok);
    }

    #[test]
    fn top_level_hash_counts_as_reference() {
        let m = json!({
            "store": {"cccc": {"last_used_at": "2026-06-07T00:00:00Z"}},
            "cpp_runtime_hash": "cccc"
        });
        assert_eq!(gc_report(&m, None).exit, ExitCode::Ok);
    }

    #[test]
    fn older_than_flags_old_shas() {
        let m = manifest_with("aaaa", "bbbb");
        let r = gc_report(&m, Some("2021-01-01"));
        assert_eq!(r.exit, ExitCode::Findings);
        let old = &r.rows.iter().find(|(k, _)| k == "old").unwrap().1;
        assert!(old.contains("bbbb"));
    }

    #[test]
    fn empty_store_is_ok() {
        let r = gc_report(&json!({"store": {}}), None);
        assert_eq!(r.exit, ExitCode::Ok);
        assert!(r.summary.contains("0 stored"));
    }

    #[test]
    fn referenced_shas_gathers_from_active_and_hash() {
        let m = json!({
            "active": {"a": {"artifacts": [{"sha256": "x"}]}},
            "go_runtime_hash": "y"
        });
        let refs = referenced_shas(&m);
        assert!(refs.contains("x"));
        assert!(refs.contains("y"));
    }
}
