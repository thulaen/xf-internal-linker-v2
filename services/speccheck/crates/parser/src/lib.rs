//! Strict `Given / When / Then` parsing for speccheck inputs.
//!
//! The parser accepts only compact behavior blocks so later report and import
//! steps can make deterministic decisions.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
/// A strict behavior block extracted from a spec or handoff file.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Behavior {
    /// Repository-relative source path.
    pub source_path: String,
    /// One-based line number of the `Given` line.
    pub line_number: usize,
    /// The given precondition text.
    pub given: String,
    /// The when action text.
    pub when: String,
    /// The then expected outcome text.
    pub then: String,
    /// The inferred target area.
    pub target_area: String,
}

/// A parser diagnostic.
#[derive(Debug, Clone, PartialEq, Eq)]
pub struct Diagnostic {
    /// One-based line number.
    pub line_number: usize,
    /// Plain-English diagnostic message.
    pub message: String,
}

/// Extract strict `Given / When / Then` blocks.
///
/// # Examples
///
/// ```
/// let text = "Given a user\nWhen they save\nThen the row appears";
/// let parsed = speccheck_parser::parse_behaviors("docs/spec.md", text);
/// assert_eq!(parsed.0.len(), 1);
/// ```
#[must_use]
pub fn parse_behaviors(source_path: &str, text: &str) -> (Vec<Behavior>, Vec<Diagnostic>) {
    let mut behaviors = Vec::new();
    let mut diagnostics = Vec::new();
    let lines: Vec<&str> = text.lines().collect();
    for index in 0..lines.len() {
        if let Some(given) = strip_keyword(lines[index], "Given") {
            match parse_one(source_path, &lines, index, given) {
                Ok(behavior) => behaviors.push(behavior),
                Err(diagnostic) => diagnostics.push(diagnostic),
            }
        }
    }
    (behaviors, diagnostics)
}

fn parse_one(
    source_path: &str,
    lines: &[&str],
    index: usize,
    given: String,
) -> Result<Behavior, Diagnostic> {
    let when_line = lines
        .get(index + 1)
        .and_then(|line| strip_keyword(line, "When"));
    let then_line = lines
        .get(index + 2)
        .and_then(|line| strip_keyword(line, "Then"));
    match (when_line, then_line) {
        (Some(when), Some(then)) => Ok(Behavior {
            source_path: source_path.to_owned(),
            line_number: index + 1,
            given,
            when,
            then,
            target_area: infer_target_area(source_path),
        }),
        _ => Err(Diagnostic {
            line_number: index + 1,
            message: "Given must be followed by exactly one When and one Then line.".to_owned(),
        }),
    }
}

fn strip_keyword(line: &str, keyword: &str) -> Option<String> {
    let trimmed = line.trim_start().trim_start_matches("**");
    let candidate = trimmed.strip_prefix(keyword)?;
    let candidate = candidate.trim_start_matches("**").trim();
    (!candidate.is_empty()).then(|| candidate.to_owned())
}

fn infer_target_area(source_path: &str) -> String {
    source_path.split('/').take(3).collect::<Vec<_>>().join("/")
}
