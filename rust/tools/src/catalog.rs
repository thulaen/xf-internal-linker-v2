//! The self-documenting catalog that `xftool list` prints.
//!
//! Each shipped subcommand has one [`CatalogEntry`]. Adding a subcommand means
//! adding its handler module and one row here, so `list` stays in lock-step with
//! what actually builds (fr-rust-cli-tooling §"Self-documenting catalog").

use crate::output::{ExitCode, ToolReport};

/// One catalog row: the command path, its category, and a one-line purpose.
pub struct CatalogEntry {
    /// The clap subcommand path, e.g. `ranking diff`.
    pub command: &'static str,
    /// The catalog category from the spec (e.g. `Ranking & scoring validity`).
    pub category: &'static str,
    /// Whether the tool can mutate state (always `false` in Wave 0).
    pub mutates: bool,
    /// One-line plain-English description.
    pub summary: &'static str,
}

/// Every subcommand shipped in this binary. Wave 0 = 8 working tools.
pub const CATALOG: &[CatalogEntry] = &[
    CatalogEntry {
        command: "ranking diff",
        category: "Ranking & scoring validity",
        mutates: false,
        summary: "Diff two ranking-run JSONs: added, removed, moved items and rank deltas.",
    },
    CatalogEntry {
        command: "score validate-breakdown",
        category: "Ranking & scoring validity",
        mutates: false,
        summary: "Assert score components sum to total within tolerance, finite, within bounds.",
    },
    CatalogEntry {
        command: "artifact check",
        category: "Artifacts & models",
        mutates: false,
        summary: "Verify an artifact's presence, sha256, and its schema/version sidecar.",
    },
    CatalogEntry {
        command: "index audit",
        category: "Search index",
        mutates: false,
        summary: "Check an index manifest for freshness, doc-count, and schema sanity.",
    },
    CatalogEntry {
        command: "bench summarize",
        category: "Benchmarks & performance",
        mutates: false,
        summary: "Parse Criterion bench output into a 3-size table/JSON summary.",
    },
    CatalogEntry {
        command: "weights lint",
        category: "Weight profiles & governance",
        mutates: false,
        summary: "Never-zero, bounds, and monotonicity checks on a weight profile.",
    },
    CatalogEntry {
        command: "log cluster-errors",
        category: "Logs & forensics",
        mutates: false,
        summary: "Group similar error log lines and count each cluster.",
    },
    CatalogEntry {
        command: "store gc-report",
        category: "Build & artifact store",
        mutates: false,
        summary: "Report unreferenced / old SHAs in the compiled-artifacts store (read-only).",
    },
];

/// Build the `xftool list` report, optionally filtered by category substring.
#[must_use]
pub fn list_report(category_filter: Option<&str>) -> ToolReport {
    let needle = category_filter.map(str::to_lowercase);
    let entries: Vec<&CatalogEntry> = CATALOG
        .iter()
        .filter(|e| {
            needle
                .as_ref()
                .is_none_or(|n| e.category.to_lowercase().contains(n))
        })
        .collect();

    let summary = format!("xftool catalog: {} subcommand(s) shown", entries.len());
    let mut report = ToolReport::new(summary, ExitCode::Ok);
    for e in entries {
        let mode = if e.mutates { "mutating" } else { "read-only" };
        report = report.row(
            e.command,
            format!("[{}] {} — {}", e.category, mode, e.summary),
        );
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn catalog_has_eight_wave0_tools() {
        // Wave 0 ships 6 of the 7 named tools (the 7th,
        // `schema_migration_checker`, is a deferred Python management command)
        // plus 2 buildable-now extras (`log cluster-errors`, `store gc-report`).
        assert_eq!(CATALOG.len(), 8);
    }

    #[test]
    fn every_entry_has_nonempty_fields() {
        for e in CATALOG {
            assert!(!e.command.is_empty());
            assert!(!e.category.is_empty());
            assert!(!e.summary.is_empty());
        }
    }

    #[test]
    fn wave0_tools_are_all_read_only() {
        assert!(CATALOG.iter().all(|e| !e.mutates));
    }

    #[test]
    fn category_filter_narrows_the_list() {
        let all = list_report(None).rows.len();
        let ranking = list_report(Some("ranking")).rows.len();
        assert!(ranking >= 1);
        assert!(ranking < all);
    }

    #[test]
    fn filter_is_case_insensitive() {
        let lower = list_report(Some("logs")).rows.len();
        let upper = list_report(Some("LOGS")).rows.len();
        assert_eq!(lower, upper);
    }
}
