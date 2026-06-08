//! `xftool index <verb-noun>` — search-index manifest audit tools.
//!
//! NOTE: Wave 0 reads a standalone index manifest JSON. When the §G
//! `search_index` crate lands, freshness/doc-count rules will be sourced from it
//! rather than re-declared in the manifest (DRY, ADR 0008 §2).

use std::path::PathBuf;

use clap::Subcommand;

use crate::output::{ExitCode, ToolReport};
use crate::util::{read_json, ToolError};

/// Default freshness budget: an index older than this many seconds is stale.
const DEFAULT_MAX_AGE_SECS: u64 = 86_400;

#[derive(Subcommand, Debug)]
pub enum IndexCmd {
    /// Check an index manifest for freshness, doc-count, and schema sanity.
    Audit {
        /// Index manifest JSON: `{ "built_at_unix": N, "now_unix"?: N, "doc_count": N, "schema_version": "..." }`.
        manifest: PathBuf,
        /// Maximum allowed index age in seconds before it is flagged stale.
        #[arg(long, default_value_t = DEFAULT_MAX_AGE_SECS)]
        max_age_secs: u64,
        /// Minimum acceptable document count (a fresh index with 0 docs is suspect).
        #[arg(long, default_value_t = 1)]
        min_docs: u64,
    },
}

impl IndexCmd {
    /// Run the selected index subcommand.
    ///
    /// # Errors
    /// Returns [`ToolError`] when the manifest cannot be read or parsed.
    pub fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::Audit {
                manifest,
                max_age_secs,
                min_docs,
            } => {
                let value = read_json(manifest)?;
                let m = parse_manifest(&value)?;
                Ok(audit_manifest(&m, *max_age_secs, *min_docs))
            }
        }
    }
}

/// Parsed index manifest fields used by the audit.
struct Manifest {
    built_at_unix: u64,
    now_unix: u64,
    doc_count: u64,
    schema_version: Option<String>,
}

fn parse_manifest(value: &serde_json::Value) -> Result<Manifest, ToolError> {
    let built_at_unix = value
        .get("built_at_unix")
        .and_then(serde_json::Value::as_u64)
        .ok_or_else(|| ToolError::usage("manifest needs a numeric 'built_at_unix' field"))?;
    let doc_count = value
        .get("doc_count")
        .and_then(serde_json::Value::as_u64)
        .ok_or_else(|| ToolError::usage("manifest needs a numeric 'doc_count' field"))?;
    // `now_unix` is optional so the tool is testable without reading the clock;
    // if absent we use the real current time.
    let now_unix = value
        .get("now_unix")
        .and_then(serde_json::Value::as_u64)
        .unwrap_or_else(current_unix);
    let schema_version = value
        .get("schema_version")
        .and_then(|v| v.as_str())
        .map(str::to_string);
    Ok(Manifest {
        built_at_unix,
        now_unix,
        doc_count,
        schema_version,
    })
}

/// Seconds since the Unix epoch, or 0 if the clock is before the epoch.
fn current_unix() -> u64 {
    std::time::SystemTime::now()
        .duration_since(std::time::UNIX_EPOCH)
        .map_or(0, |d| d.as_secs())
}

/// Audit freshness, doc-count, and schema presence. Exit `Findings` on any issue.
fn audit_manifest(m: &Manifest, max_age_secs: u64, min_docs: u64) -> ToolReport {
    let mut violations: Vec<String> = Vec::new();

    // `saturating_sub` keeps a future `built_at` (clock skew) from underflowing.
    let age = m.now_unix.saturating_sub(m.built_at_unix);
    if m.built_at_unix > m.now_unix {
        violations.push("built_at is in the future relative to now (clock skew?)".to_string());
    }
    if age > max_age_secs {
        violations.push(format!(
            "index is stale: age {age}s exceeds max {max_age_secs}s"
        ));
    }
    if m.doc_count < min_docs {
        violations.push(format!(
            "doc_count {} is below minimum {min_docs}",
            m.doc_count
        ));
    }
    if m.schema_version.is_none() {
        violations.push("manifest has no 'schema_version' field".to_string());
    }

    let exit = if violations.is_empty() {
        ExitCode::Ok
    } else {
        ExitCode::Findings
    };
    let summary = if violations.is_empty() {
        format!("index audit ok: {} docs, age {age}s", m.doc_count)
    } else {
        format!("index audit: {} issue(s)", violations.len())
    };
    let mut report = ToolReport::new(summary, exit)
        .row("age_secs", age.to_string())
        .row("doc_count", m.doc_count.to_string())
        .row(
            "schema_version",
            m.schema_version
                .clone()
                .unwrap_or_else(|| "(missing)".to_string()),
        );
    for (i, v) in violations.iter().enumerate() {
        report = report.row(format!("issue_{}", i + 1), v.clone());
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;

    fn manifest(built: u64, now: u64, docs: u64) -> Manifest {
        Manifest {
            built_at_unix: built,
            now_unix: now,
            doc_count: docs,
            schema_version: Some("v1".into()),
        }
    }

    #[test]
    fn fresh_populated_index_passes() {
        let r = audit_manifest(&manifest(1000, 1500, 42), DEFAULT_MAX_AGE_SECS, 1);
        assert_eq!(r.exit, ExitCode::Ok);
    }

    #[test]
    fn stale_index_is_flagged() {
        let r = audit_manifest(&manifest(0, 100_000, 42), 1000, 1);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("stale")));
    }

    #[test]
    fn empty_index_is_flagged() {
        let r = audit_manifest(&manifest(1000, 1500, 0), DEFAULT_MAX_AGE_SECS, 1);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("below minimum")));
    }

    #[test]
    fn future_build_time_flagged_and_does_not_panic() {
        let r = audit_manifest(&manifest(2000, 1000, 5), DEFAULT_MAX_AGE_SECS, 1);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("future")));
    }

    #[test]
    fn missing_schema_flagged() {
        let mut m = manifest(1000, 1500, 5);
        m.schema_version = None;
        let r = audit_manifest(&m, DEFAULT_MAX_AGE_SECS, 1);
        assert_eq!(r.exit, ExitCode::Findings);
    }

    #[test]
    fn parse_requires_built_at_and_doc_count() {
        assert!(parse_manifest(&json!({"doc_count": 1})).is_err());
        assert!(parse_manifest(&json!({"built_at_unix": 1})).is_err());
    }

    #[test]
    fn parse_uses_optional_now_unix() {
        let m =
            parse_manifest(&json!({"built_at_unix": 1, "now_unix": 5, "doc_count": 2})).unwrap();
        assert_eq!(m.now_unix, 5);
    }
}
