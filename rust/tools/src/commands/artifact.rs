//! `xftool artifact <verb-noun>` — artifact integrity tools.
//!
//! NOTE: Wave 0 verifies a file against a declared sidecar. When the §G
//! artifact-validation crate lands, the sha256 + schema/version rules will be
//! shared with the app's validator instead of re-encoded here (ADR 0008 §2).

use std::path::{Path, PathBuf};

use clap::Subcommand;
use sha2::{Digest, Sha256};

use crate::output::{ExitCode, ToolReport};
use crate::util::{parse_json, read_file, ToolError};

#[derive(Subcommand, Debug)]
pub enum ArtifactCmd {
    /// Verify an artifact's presence, sha256, and schema/version sidecar.
    Check {
        /// Path to the artifact file.
        artifact: PathBuf,
        /// Sidecar JSON (defaults to `<artifact>.meta.json`):
        /// `{ "sha256": "...", "schema": "...", "version": "..." }`.
        #[arg(long)]
        sidecar: Option<PathBuf>,
    },
}

impl ArtifactCmd {
    /// Run the selected artifact subcommand.
    ///
    /// # Errors
    /// Returns [`ToolError`] when the sidecar cannot be read or parsed.
    pub fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::Check { artifact, sidecar } => {
                let sidecar_path = sidecar.clone().unwrap_or_else(|| default_sidecar(artifact));
                let sidecar_text = read_file(&sidecar_path)?;
                let meta = parse_json(&sidecar_text, &sidecar_path.display().to_string())?;
                Ok(check_artifact(artifact, &meta))
            }
        }
    }
}

/// `<artifact>.meta.json` next to the artifact.
fn default_sidecar(artifact: &Path) -> PathBuf {
    let mut name = artifact.as_os_str().to_os_string();
    name.push(".meta.json");
    PathBuf::from(name)
}

/// Verify presence + sha256 + declared schema/version. Exit `Findings` on any
/// mismatch, `Ok` when everything matches. A missing artifact is a finding, not
/// a usage error, so CI sees exit 1 (not 2).
fn check_artifact(artifact: &Path, meta: &serde_json::Value) -> ToolReport {
    let mut violations: Vec<String> = Vec::new();

    let bytes = match std::fs::read(artifact) {
        Ok(b) => Some(b),
        Err(e) => {
            violations.push(format!(
                "artifact '{}' is missing or unreadable: {e}",
                artifact.display()
            ));
            None
        }
    };

    let mut actual_sha = String::from("(not computed)");
    if let Some(bytes) = &bytes {
        actual_sha = sha256_hex(bytes);
        if let Some(expected) = meta.get("sha256").and_then(|v| v.as_str()) {
            if !expected.eq_ignore_ascii_case(&actual_sha) {
                violations.push(format!(
                    "sha256 mismatch: expected {expected}, got {actual_sha}"
                ));
            }
        } else {
            violations.push("sidecar has no 'sha256' field to verify against".to_string());
        }
    }

    // Schema and version are declarative: their presence in the sidecar is the
    // contract. A missing declared field is a finding.
    if meta.get("schema").and_then(|v| v.as_str()).is_none() {
        violations.push("sidecar has no 'schema' field".to_string());
    }
    if meta.get("version").and_then(|v| v.as_str()).is_none() {
        violations.push("sidecar has no 'version' field".to_string());
    }

    let exit = if violations.is_empty() {
        ExitCode::Ok
    } else {
        ExitCode::Findings
    };
    let summary = if violations.is_empty() {
        format!("artifact '{}' verified", artifact.display())
    } else {
        format!(
            "artifact '{}' failed: {} issue(s)",
            artifact.display(),
            violations.len()
        )
    };
    let mut report = ToolReport::new(summary, exit)
        .row("sha256", actual_sha)
        .row(
            "schema",
            meta.get("schema")
                .and_then(|v| v.as_str())
                .unwrap_or("(missing)")
                .to_string(),
        )
        .row(
            "version",
            meta.get("version")
                .and_then(|v| v.as_str())
                .unwrap_or("(missing)")
                .to_string(),
        );
    for (i, v) in violations.iter().enumerate() {
        report = report.row(format!("issue_{}", i + 1), v.clone());
    }
    report
}

/// Lowercase hex sha256 of the given bytes.
fn sha256_hex(bytes: &[u8]) -> String {
    use std::fmt::Write as _;
    let digest = Sha256::digest(bytes);
    let mut s = String::with_capacity(digest.len() * 2);
    for byte in digest {
        // Writing to a String is infallible; the Result is intentionally ignored.
        let _ = write!(s, "{byte:02x}");
    }
    s
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use std::io::Write;

    fn temp_file(name: &str, contents: &[u8]) -> PathBuf {
        let mut path = std::env::temp_dir();
        path.push(format!("xftool-artifact-{name}-{}", std::process::id()));
        let mut f = std::fs::File::create(&path).unwrap();
        f.write_all(contents).unwrap();
        path
    }

    #[test]
    fn sha256_hex_is_known_vector() {
        // sha256("") is well-known.
        assert_eq!(
            sha256_hex(b""),
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
        );
    }

    #[test]
    fn matching_sidecar_passes() {
        let path = temp_file("ok", b"hello");
        let sha = sha256_hex(b"hello");
        let meta = json!({"sha256": sha, "schema": "demo", "version": "1.0"});
        let r = check_artifact(&path, &meta);
        assert_eq!(r.exit, ExitCode::Ok);
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn wrong_sha_is_finding() {
        let path = temp_file("bad", b"hello");
        let meta = json!({"sha256": "deadbeef", "schema": "demo", "version": "1.0"});
        let r = check_artifact(&path, &meta);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("mismatch")));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn missing_artifact_is_finding_not_error() {
        let meta = json!({"sha256": "x", "schema": "s", "version": "1"});
        let r = check_artifact(Path::new("/no/such/xftool-artifact"), &meta);
        assert_eq!(r.exit, ExitCode::Findings);
    }

    #[test]
    fn missing_schema_and_version_flagged() {
        let path = temp_file("nometa", b"data");
        let sha = sha256_hex(b"data");
        let meta = json!({"sha256": sha});
        let r = check_artifact(&path, &meta);
        assert_eq!(r.exit, ExitCode::Findings);
        assert!(r.rows.iter().any(|(_, v)| v.contains("no 'schema'")));
        assert!(r.rows.iter().any(|(_, v)| v.contains("no 'version'")));
        let _ = std::fs::remove_file(&path);
    }

    #[test]
    fn default_sidecar_appends_suffix() {
        let p = default_sidecar(Path::new("/a/b.bin"));
        assert!(p.to_string_lossy().ends_with("b.bin.meta.json"));
    }
}
