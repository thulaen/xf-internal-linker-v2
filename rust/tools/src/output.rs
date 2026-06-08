//! Shared output / formatting for every `xftool` subcommand (DRY).
//!
//! One place owns: the `--format json|table|csv` enum, rendering a simple
//! row-based report in all three formats, and the CI exit-code contract
//! (`0` ok, `1` findings, `2` error). Every subcommand returns a
//! [`ToolReport`]; `main` renders it once and exits with its code.

use std::fmt::Write as _;

use clap::ValueEnum;
use serde::Serialize;

/// Output format shared by every subcommand. Default is `table` (human),
/// `json` is for CI, `csv` for spreadsheets / `duckdb`.
#[derive(Copy, Clone, Debug, PartialEq, Eq, ValueEnum, Default)]
#[clap(rename_all = "lower")]
pub enum Format {
    /// Human-readable aligned columns (default).
    #[default]
    Table,
    /// Machine-readable JSON for CI consumers.
    Json,
    /// Comma-separated values.
    Csv,
}

/// CI exit codes, fixed by the subcommand contract (fr-rust-cli-tooling §Framework).
#[derive(Copy, Clone, Debug, PartialEq, Eq)]
pub enum ExitCode {
    /// Everything checked out.
    Ok = 0,
    /// The tool ran fine but found violations / findings.
    Findings = 1,
    /// Usage or internal error.
    Error = 2,
}

/// A finished subcommand result: a short headline, zero or more named rows,
/// and the exit code the process should end with.
///
/// `rows` is a list of `(key, value)` pairs so every tool renders the same way
/// in every format without each tool re-implementing table/CSV/JSON logic.
#[derive(Debug, Clone, Serialize)]
pub struct ToolReport {
    /// One-line summary shown at the top of `table` output.
    pub summary: String,
    /// Ordered detail rows (`key`, `value`).
    pub rows: Vec<(String, String)>,
    /// Exit code (not serialized into the JSON body; used by `main`).
    #[serde(skip)]
    pub exit: ExitCode,
}

impl ToolReport {
    /// Build an empty report with the given summary and exit code.
    #[must_use]
    pub fn new(summary: impl Into<String>, exit: ExitCode) -> Self {
        Self {
            summary: summary.into(),
            rows: Vec::new(),
            exit,
        }
    }

    /// Append one `(key, value)` detail row (builder style).
    #[must_use]
    pub fn row(mut self, key: impl Into<String>, value: impl Into<String>) -> Self {
        self.rows.push((key.into(), value.into()));
        self
    }

    /// Render this report to a `String` in the requested format.
    #[must_use]
    pub fn render(&self, format: Format) -> String {
        match format {
            Format::Table => self.render_table(),
            Format::Json => self.render_json(),
            Format::Csv => self.render_csv(),
        }
    }

    fn render_table(&self) -> String {
        let mut out = String::new();
        out.push_str(&self.summary);
        out.push('\n');
        let width = self.rows.iter().map(|(k, _)| k.len()).max().unwrap_or(0);
        for (k, v) in &self.rows {
            // `write!` to a String is infallible; the result is intentionally ignored.
            let _ = writeln!(out, "  {k:<width$}  {v}");
        }
        out
    }

    fn render_json(&self) -> String {
        // A serialization failure here is an internal bug, not user input, so a
        // fixed fallback object is the honest result rather than a panic.
        serde_json::to_string_pretty(self)
            .unwrap_or_else(|_| "{\"error\":\"serialization failed\"}".to_string())
    }

    fn render_csv(&self) -> String {
        let mut out = String::from("key,value\n");
        for (k, v) in &self.rows {
            let _ = writeln!(out, "{},{}", csv_escape(k), csv_escape(v));
        }
        out
    }
}

/// Quote a CSV field when it contains a comma, quote, or newline (RFC 4180).
fn csv_escape(field: &str) -> String {
    if field.contains([',', '"', '\n']) {
        format!("\"{}\"", field.replace('"', "\"\""))
    } else {
        field.to_string()
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn table_render_aligns_keys_and_shows_summary() {
        let r = ToolReport::new("done", ExitCode::Ok)
            .row("a", "1")
            .row("longkey", "2");
        let out = r.render(Format::Table);
        assert!(out.starts_with("done\n"));
        assert!(out.contains("a        1"));
        assert!(out.contains("longkey  2"));
    }

    #[test]
    fn json_render_is_parseable_and_has_rows() {
        let r = ToolReport::new("s", ExitCode::Findings).row("k", "v");
        let parsed: serde_json::Value = serde_json::from_str(&r.render(Format::Json)).unwrap();
        assert_eq!(parsed["summary"], "s");
        assert_eq!(parsed["rows"][0][0], "k");
        assert_eq!(parsed["rows"][0][1], "v");
    }

    #[test]
    fn csv_render_has_header_and_escapes_commas() {
        let r = ToolReport::new("s", ExitCode::Ok).row("name", "a,b");
        let out = r.render(Format::Csv);
        assert!(out.starts_with("key,value\n"));
        assert!(out.contains("name,\"a,b\""));
    }

    #[test]
    fn csv_escape_doubles_quotes() {
        assert_eq!(csv_escape("he\"llo"), "\"he\"\"llo\"");
        assert_eq!(csv_escape("plain"), "plain");
    }
}
