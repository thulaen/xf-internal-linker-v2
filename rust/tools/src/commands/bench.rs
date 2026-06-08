//! `xftool bench <verb-noun>` — benchmark output tools.
//!
//! NOTE: Wave 0 parses Criterion's plain-text estimate lines. When a structured
//! Criterion JSON export is wired into the repo, this will read that instead of
//! scraping the human output (DRY, ADR 0008 §2).

use std::path::PathBuf;

use clap::Subcommand;

use crate::output::{ExitCode, ToolReport};
use crate::util::{read_file, ToolError};

#[derive(Subcommand, Debug)]
pub enum BenchCmd {
    /// Parse Criterion bench output into a per-benchmark time summary.
    Summarize {
        /// File containing captured Criterion stdout.
        output: PathBuf,
    },
}

impl BenchCmd {
    /// Run the selected bench subcommand.
    ///
    /// # Errors
    /// Returns [`ToolError`] when the output file cannot be read.
    pub fn run(&self) -> Result<ToolReport, ToolError> {
        match self {
            Self::Summarize { output } => {
                let text = read_file(output)?;
                Ok(summarize(&text))
            }
        }
    }
}

/// One parsed benchmark: its name and the central time estimate (the middle
/// value Criterion prints on the `time:` line).
#[derive(Debug, PartialEq)]
struct BenchResult {
    name: String,
    time: String,
}

/// Parse Criterion's `<name>   time:   [lo  mid  hi]` lines.
///
/// Criterion prints one line per benchmark id with the central-estimate bracket
/// after a `time:` marker on the same line. The id is everything before
/// `time:`; the central estimate is the middle `value unit` pair inside the
/// brackets. Each of the three repo sizes (e.g. `/64`, `/1024`, `/16384`)
/// becomes a row.
fn parse_results(text: &str) -> Vec<BenchResult> {
    text.lines().filter_map(parse_line).collect()
}

/// Parse one `<name>   time:   [lo mid hi]` line into a [`BenchResult`].
fn parse_line(line: &str) -> Option<BenchResult> {
    // Split on the first `time:` marker; the left side is the benchmark id.
    let idx = line.find("time:")?;
    let name = line[..idx].trim();
    if name.is_empty() {
        return None;
    }
    let time = parse_time_bracket(line[idx + "time:".len()..].trim())?;
    Some(BenchResult {
        name: name.to_string(),
        time,
    })
}

/// Extract the central estimate from a `[lo mid hi]` bracket.
fn parse_time_bracket(rest: &str) -> Option<String> {
    let inner = rest.strip_prefix('[')?.strip_suffix(']')?;
    // Criterion prints "lo unit  mid unit  hi unit"; the central estimate is the
    // middle "value unit" pair. Split into whitespace tokens and take tokens 2-3.
    let tokens: Vec<&str> = inner.split_whitespace().collect();
    if tokens.len() == 6 {
        Some(format!("{} {}", tokens[2], tokens[3]))
    } else {
        // Unknown shape: return the whole bracket so nothing is silently dropped.
        Some(inner.trim().to_string())
    }
}

/// Build the summary report. Always exit `Ok` (this is a reporter, not a gate);
/// an empty parse still reports zero benchmarks honestly.
fn summarize(text: &str) -> ToolReport {
    let results = parse_results(text);
    let summary = format!("bench summarize: {} benchmark(s) parsed", results.len());
    let mut report = ToolReport::new(summary, ExitCode::Ok);
    for r in &results {
        report = report.row(r.name.clone(), r.time.clone());
    }
    report
}

#[cfg(test)]
mod tests {
    use super::*;

    const SAMPLE: &str = "\
l2norm/64               time:   [120.11 ns 121.00 ns 122.30 ns]
                        change: [-1.0% +0.2% +1.3%] (p = 0.74 > 0.05)
l2norm/1024             time:   [1.8000 us 1.8123 us 1.8260 us]
l2norm/16384            time:   [28.100 us 28.450 us 28.900 us]
Found 3 outliers among 100 measurements (3.00%)";

    #[test]
    fn parses_three_sizes() {
        let results = parse_results(SAMPLE);
        assert_eq!(results.len(), 3);
        assert_eq!(
            results[0],
            BenchResult {
                name: "l2norm/64".into(),
                time: "121.00 ns".into()
            }
        );
        assert_eq!(results[1].name, "l2norm/1024");
        assert_eq!(results[2].name, "l2norm/16384");
    }

    #[test]
    fn central_estimate_is_the_middle_value() {
        let results = parse_results(SAMPLE);
        assert_eq!(results[1].time, "1.8123 us");
    }

    #[test]
    fn summarize_reports_count_and_is_ok() {
        let r = summarize(SAMPLE);
        assert_eq!(r.exit, ExitCode::Ok);
        assert!(r.summary.contains("3 benchmark"));
        assert_eq!(r.rows.len(), 3);
    }

    #[test]
    fn empty_input_reports_zero() {
        let r = summarize("");
        assert!(r.summary.contains("0 benchmark"));
    }

    #[test]
    fn time_bracket_without_six_tokens_keeps_bracket() {
        assert_eq!(parse_time_bracket("[fast]"), Some("fast".to_string()));
    }

    #[test]
    fn line_without_time_marker_is_skipped() {
        assert!(parse_line("Benchmarking l2norm/64: Warming up").is_none());
    }
}
