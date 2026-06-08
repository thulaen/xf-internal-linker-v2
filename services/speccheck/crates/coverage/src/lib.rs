//! Coverage and mutation gap data types for speccheck.
//!
//! The first release exposes the shared gap shape that later parsers use for
//! language-specific coverage and mutation reports.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use std::fmt::{Display, Formatter};

use serde_json::Value;

/// A cross-language coverage or mutation gap.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Gap {
    /// Language name.
    pub language: String,
    /// Repo-relative file path.
    pub file: String,
    /// First affected line.
    pub line_start: u32,
    /// Last affected line.
    pub line_end: u32,
    /// Gap kind.
    pub kind: String,
}

/// A parse failure from a coverage or mutation report.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct CoverageParseError {
    message: String,
}

impl Display for CoverageParseError {
    fn fmt(&self, formatter: &mut Formatter<'_>) -> std::fmt::Result {
        formatter.write_str(&self.message)
    }
}

/// Parse LCOV text into stable uncovered gap clusters.
///
/// # Errors
///
/// Returns an error when an LCOV line or branch record has a malformed line
/// number or an unexpected field shape.
///
/// # Examples
///
/// ```
/// use speccheck_coverage::parse_lcov;
///
/// let gaps = parse_lcov("rust", "SF:src/lib.rs\nDA:7,0\nend_of_record\n")
///     .expect("LCOV should parse");
/// assert_eq!(gaps[0].line_start, 7);
/// ```
pub fn parse_lcov(language: &str, report: &str) -> Result<Vec<Gap>, CoverageParseError> {
    let mut gaps = Vec::new();
    let mut current_file = String::new();
    let mut uncovered_lines = Vec::new();
    let mut uncovered_branches = Vec::new();
    for line in report.lines() {
        let line = line.trim();
        if line.is_empty() {
            continue;
        }
        if line.starts_with("TN:") {
            continue;
        }
        if let Some(path) = line.strip_prefix("SF:") {
            flush_file(
                &mut gaps,
                language,
                &current_file,
                &mut uncovered_lines,
                &mut uncovered_branches,
            );
            current_file = path.to_string();
            continue;
        }
        if let Some(payload) = line.strip_prefix("DA:") {
            let (line_number, count) = parse_pair(payload, "DA")?;
            if count == "0" {
                uncovered_lines.push(line_number);
            }
            continue;
        }
        if let Some(payload) = line.strip_prefix("BRDA:") {
            let (line_number, taken) = parse_branch(payload)?;
            if taken == "-" || taken == "0" {
                uncovered_branches.push(line_number);
            }
            continue;
        }
        if line == "end_of_record" {
            flush_file(
                &mut gaps,
                language,
                &current_file,
                &mut uncovered_lines,
                &mut uncovered_branches,
            );
            current_file.clear();
        }
    }
    flush_file(
        &mut gaps,
        language,
        &current_file,
        &mut uncovered_lines,
        &mut uncovered_branches,
    );
    Ok(gaps)
}

/// Parse Cobertura XML text into stable uncovered gap clusters.
///
/// # Errors
///
/// Returns an error when a class is missing `filename`, a line is outside a
/// class, or a line number is malformed.
///
/// # Examples
///
/// ```
/// use speccheck_coverage::parse_cobertura;
///
/// let xml = r#"<class filename="src/lib.rs"><line number="9" hits="0"/></class>"#;
/// let gaps = parse_cobertura("rust", xml).expect("Cobertura should parse");
/// assert_eq!(gaps[0].line_start, 9);
/// ```
pub fn parse_cobertura(language: &str, report: &str) -> Result<Vec<Gap>, CoverageParseError> {
    let mut gaps = Vec::new();
    let mut current_file = String::new();
    let mut uncovered_lines = Vec::new();
    let mut uncovered_branches = Vec::new();
    for line in report.lines() {
        let line = line.trim();
        if is_cobertura_class_tag(line) {
            flush_file(
                &mut gaps,
                language,
                &current_file,
                &mut uncovered_lines,
                &mut uncovered_branches,
            );
            current_file = attr_value(line, "filename")
                .ok_or_else(|| parse_error("Cobertura class is missing filename"))?
                .to_string();
        }
        if is_cobertura_line_tag(line) {
            parse_cobertura_line(
                line,
                &current_file,
                &mut uncovered_lines,
                &mut uncovered_branches,
            )?;
        }
        if line.contains("</class>") {
            flush_file(
                &mut gaps,
                language,
                &current_file,
                &mut uncovered_lines,
                &mut uncovered_branches,
            );
            current_file.clear();
        }
    }
    flush_file(
        &mut gaps,
        language,
        &current_file,
        &mut uncovered_lines,
        &mut uncovered_branches,
    );
    Ok(gaps)
}

/// Parse cargo-mutants `outcomes.json` text into surviving mutant gaps.
///
/// # Errors
///
/// Returns an error when the JSON is invalid or when a missed or timed-out
/// mutant lacks a source file or line number.
///
/// # Examples
///
/// ```
/// use speccheck_coverage::parse_cargo_mutants;
///
/// let json = r#"{"outcomes":[{"outcome":"missed","mutant":{"file":"src/lib.rs","line":4}}]}"#;
/// let gaps = parse_cargo_mutants("rust", json).expect("cargo-mutants should parse");
/// assert_eq!(gaps[0].kind, "surviving_mutant");
/// ```
pub fn parse_cargo_mutants(language: &str, report: &str) -> Result<Vec<Gap>, CoverageParseError> {
    let value: Value =
        serde_json::from_str(report).map_err(|_| parse_error("cargo-mutants JSON is invalid"))?;
    let mut gaps = Vec::new();
    collect_mutant_survivors(language, &value, &mut gaps)?;
    gaps.sort_by(|left, right| {
        left.file
            .cmp(&right.file)
            .then(left.line_start.cmp(&right.line_start))
    });
    gaps.dedup_by(|left, right| left.file == right.file && left.line_start == right.line_start);
    Ok(gaps)
}

fn parse_cobertura_line(
    line: &str,
    current_file: &str,
    uncovered_lines: &mut Vec<u32>,
    uncovered_branches: &mut Vec<u32>,
) -> Result<(), CoverageParseError> {
    if current_file.is_empty() {
        return Err(parse_error("Cobertura line appears before class filename"));
    }
    let line_number = attr_value(line, "number")
        .ok_or_else(|| parse_error("Cobertura line is missing line number"))
        .and_then(|value| parse_line_number(value, "Cobertura"))?;
    if attr_value(line, "hits") == Some("0") {
        uncovered_lines.push(line_number);
    }
    let is_branch = attr_value(line, "branch") == Some("true");
    let is_fully_covered =
        attr_value(line, "condition-coverage").is_some_and(|value| value.starts_with("100%"));
    if is_branch && !is_fully_covered {
        uncovered_branches.push(line_number);
    }
    Ok(())
}

fn is_cobertura_class_tag(line: &str) -> bool {
    line.contains("<class ") || line.contains("<class>")
}

fn is_cobertura_line_tag(line: &str) -> bool {
    line.contains("<line ") || line.contains("<line>")
}

fn collect_mutant_survivors(
    language: &str,
    value: &Value,
    gaps: &mut Vec<Gap>,
) -> Result<(), CoverageParseError> {
    match value {
        Value::Array(items) => {
            for item in items {
                collect_mutant_survivors(language, item, gaps)?;
            }
        }
        Value::Object(object) => {
            if is_surviving_mutant(object) {
                let file = find_string_value(
                    value,
                    &["file", "filename", "source_file", "source_path", "path"],
                )
                .ok_or_else(|| parse_error("cargo-mutants survivor is missing file"))?;
                let line = find_u32_value(value, &["line", "line_start", "start_line"])
                    .ok_or_else(|| parse_error("cargo-mutants survivor is missing line"))?;
                push_gap(gaps, language, file, "surviving_mutant", line, line);
                return Ok(());
            }
            for child in object.values() {
                collect_mutant_survivors(language, child, gaps)?;
            }
        }
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => {}
    }
    Ok(())
}

fn is_surviving_mutant(object: &serde_json::Map<String, Value>) -> bool {
    for name in ["outcome", "result", "status"] {
        if let Some(text) = object.get(name).and_then(Value::as_str) {
            let lower = text.to_ascii_lowercase();
            return lower == "missed" || lower == "timeout";
        }
    }
    false
}

fn find_string_value<'a>(value: &'a Value, names: &[&str]) -> Option<&'a str> {
    match value {
        Value::Object(object) => {
            for name in names {
                if let Some(text) = object.get(*name).and_then(Value::as_str) {
                    return Some(text);
                }
            }
            for child in object.values() {
                if let Some(text) = find_string_value(child, names) {
                    return Some(text);
                }
            }
            None
        }
        Value::Array(items) => items
            .iter()
            .find_map(|child| find_string_value(child, names)),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => None,
    }
}

fn find_u32_value(value: &Value, names: &[&str]) -> Option<u32> {
    match value {
        Value::Object(object) => {
            for name in names {
                if let Some(number) = object
                    .get(*name)
                    .and_then(Value::as_u64)
                    .and_then(|number| u32::try_from(number).ok())
                {
                    return Some(number);
                }
            }
            for child in object.values() {
                if let Some(number) = find_u32_value(child, names) {
                    return Some(number);
                }
            }
            None
        }
        Value::Array(items) => items.iter().find_map(|child| find_u32_value(child, names)),
        Value::Null | Value::Bool(_) | Value::Number(_) | Value::String(_) => None,
    }
}

fn attr_value<'a>(text: &'a str, name: &str) -> Option<&'a str> {
    let needle = format!("{name}=\"");
    let start = text.find(&needle)? + needle.len();
    let rest = &text[start..];
    let end = rest.find('"')?;
    Some(&rest[..end])
}

fn parse_pair<'a>(payload: &'a str, tag: &str) -> Result<(u32, &'a str), CoverageParseError> {
    let Some((line_number, count)) = payload.split_once(',') else {
        return Err(parse_error(format!("{tag} record is missing a comma")));
    };
    Ok((parse_line_number(line_number, tag)?, count))
}

fn parse_branch(payload: &str) -> Result<(u32, &str), CoverageParseError> {
    let fields = payload.split(',').collect::<Vec<_>>();
    if fields.len() != 4 {
        return Err(parse_error("BRDA record must have four fields"));
    }
    Ok((parse_line_number(fields[0], "BRDA")?, fields[3]))
}

fn parse_line_number(value: &str, tag: &str) -> Result<u32, CoverageParseError> {
    value
        .parse::<u32>()
        .map_err(|_| parse_error(format!("{tag} line number is invalid")))
}

fn flush_file(
    gaps: &mut Vec<Gap>,
    language: &str,
    current_file: &str,
    uncovered_lines: &mut Vec<u32>,
    uncovered_branches: &mut Vec<u32>,
) {
    if current_file.is_empty() {
        return;
    }
    push_clusters(
        gaps,
        language,
        current_file,
        "uncovered_line",
        uncovered_lines,
    );
    push_clusters(
        gaps,
        language,
        current_file,
        "uncovered_branch",
        uncovered_branches,
    );
}

fn push_clusters(
    gaps: &mut Vec<Gap>,
    language: &str,
    file: &str,
    kind: &str,
    lines: &mut Vec<u32>,
) {
    lines.sort_unstable();
    lines.dedup();
    let mut cluster_start = None;
    let mut previous = 0;
    for line in lines.drain(..) {
        match cluster_start {
            Some(_) if line == previous + 1 => previous = line,
            Some(start) => {
                push_gap(gaps, language, file, kind, start, previous);
                cluster_start = Some(line);
                previous = line;
            }
            None => {
                cluster_start = Some(line);
                previous = line;
            }
        }
    }
    if let Some(start) = cluster_start {
        push_gap(gaps, language, file, kind, start, previous);
    }
}

fn push_gap(
    gaps: &mut Vec<Gap>,
    language: &str,
    file: &str,
    kind: &str,
    line_start: u32,
    line_end: u32,
) {
    gaps.push(Gap {
        language: language.to_string(),
        file: file.to_string(),
        line_start,
        line_end,
        kind: kind.to_string(),
    });
}

fn parse_error(message: impl Into<String>) -> CoverageParseError {
    CoverageParseError {
        message: message.into(),
    }
}
