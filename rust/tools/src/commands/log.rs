//! `xftool log <verb-noun>` — log forensics tools.

use std::path::PathBuf;

use clap::Subcommand;

use crate::output::{ExitCode, ToolReport};
use crate::util::{read_file, ToolError};

/// Default number of top clusters to show.
const DEFAULT_TOP: usize = 20;

#[derive(Subcommand, Debug)]
pub enum LogCmd {
    /// Group similar error log lines and count each cluster.
    ClusterErrors {
        /// Log file to scan.
        logfile: PathBuf,
        /// Show only the top N clusters by count.
        #[arg(long, default_value_t = DEFAULT_TOP)]
        top: usize,
    },
}

impl LogCmd {
    /// Run the selected log subcommand.
    ///
    /// # Errors
    /// Returns [`ToolError`] when the log file cannot be read.
    pub fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::ClusterErrors { logfile, top } => {
                let text = read_file(logfile)?;
                Ok(cluster_errors(&text, *top))
            }
        }
    }
}

/// A line counts as an error when it contains a common severity keyword.
fn is_error_line(line: &str) -> bool {
    let lower = line.to_lowercase();
    [
        "error",
        "exception",
        "panic",
        "traceback",
        "fatal",
        "critical",
    ]
    .iter()
    .any(|kw| lower.contains(kw))
}

/// Normalize an error line into a cluster key by removing the volatile parts
/// (numbers, hex, quoted strings, timestamps) so "user 12 failed" and
/// "user 99 failed" land in the same cluster.
fn cluster_key(line: &str) -> String {
    let mut key = String::with_capacity(line.len());
    let mut chars = line.chars().peekable();
    while let Some(c) = chars.next() {
        if c.is_ascii_digit() {
            // Collapse a run of digits to a single '#'.
            if !key.ends_with('#') {
                key.push('#');
            }
            while chars.peek().is_some_and(char::is_ascii_digit) {
                chars.next();
            }
        } else if c == '"' || c == '\'' {
            // Drop quoted payloads entirely.
            if !key.ends_with('Q') {
                key.push('Q');
            }
            while let Some(&n) = chars.peek() {
                chars.next();
                if n == c {
                    break;
                }
            }
        } else {
            key.push(c);
        }
    }
    key.split_whitespace().collect::<Vec<_>>().join(" ")
}

/// Cluster error lines by normalized key, count each, and report the top N.
/// Exit `Findings` when any error lines exist, `Ok` when the log is clean.
fn cluster_errors(text: &str, top: usize) -> ToolReport {
    let mut counts: std::collections::HashMap<String, (usize, String)> =
        std::collections::HashMap::new();
    let mut total = 0usize;

    for line in text.lines() {
        let trimmed = line.trim();
        if trimmed.is_empty() || !is_error_line(trimmed) {
            continue;
        }
        total += 1;
        let key = cluster_key(trimmed);
        let entry = counts
            .entry(key)
            .or_insert_with(|| (0, trimmed.to_string()));
        entry.0 += 1;
    }

    let mut clusters: Vec<(usize, String)> = counts.into_values().collect();
    clusters.sort_by(|a, b| b.0.cmp(&a.0).then_with(|| a.1.cmp(&b.1)));

    let exit = if total == 0 {
        ExitCode::Ok
    } else {
        ExitCode::Findings
    };
    let summary = format!(
        "log cluster-errors: {} error line(s) in {} cluster(s)",
        total,
        clusters.len()
    );
    let mut report = ToolReport::new(summary, exit);
    for (count, sample) in clusters.iter().take(top) {
        report = report.row(format!("x{count}"), sample.clone());
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn groups_lines_differing_only_by_numbers() {
        let log = "ERROR user 12 failed\nERROR user 99 failed\nINFO ok\n";
        let r = cluster_errors(log, DEFAULT_TOP);
        assert_eq!(r.exit, ExitCode::Findings);
        // Two error lines, one cluster.
        assert!(r.summary.contains("2 error line(s) in 1 cluster"));
    }

    #[test]
    fn clean_log_is_ok() {
        let r = cluster_errors("INFO all good\nDEBUG fine\n", DEFAULT_TOP);
        assert_eq!(r.exit, ExitCode::Ok);
        assert!(r.summary.contains("0 error line(s)"));
    }

    #[test]
    fn distinct_errors_are_separate_clusters() {
        let log = "ERROR disk full\nException timeout\n";
        let r = cluster_errors(log, DEFAULT_TOP);
        assert!(r.summary.contains("2 cluster"));
    }

    #[test]
    fn top_limits_rows() {
        let log = "ERROR a\nException b\npanic c\nfatal d\n";
        let r = cluster_errors(log, 2);
        assert_eq!(r.rows.len(), 2);
    }

    #[test]
    fn cluster_key_collapses_digits_and_quotes() {
        assert_eq!(cluster_key("user 12 said \"hi\""), "user # said Q");
    }

    #[test]
    fn is_error_line_matches_keywords_case_insensitive() {
        assert!(is_error_line("FATAL boom"));
        assert!(is_error_line("a Traceback here"));
        assert!(!is_error_line("just info"));
    }
}
