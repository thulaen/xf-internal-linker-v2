//! Canonical JSON report helpers for speccheck.
//!
//! Report output keeps a stable top-level shape so the Django importer can
//! reject drift and dedupe findings consistently.

#![forbid(unsafe_code)]
#![allow(clippy::pedantic, clippy::nursery, clippy::cargo)]
use serde_json::{json, Value};
use speccheck_coverage::Gap;
use speccheck_detectors::Finding;
use speccheck_parser::Behavior;

/// Build the canonical empty report shape.
///
/// # Examples
///
/// ```
/// let report = speccheck_report::empty_report_json();
/// assert!(report.contains("\"bug_candidates\":[]"));
/// ```
#[must_use]
pub fn empty_report_json() -> String {
    concat!(
        "{\"bug_candidates\":[],",
        "\"duplicate_warnings\":[],",
        "\"metadata\":{},",
        "\"parsed_behaviors\":[],",
        "\"stale_record_warnings\":[],",
        "\"summary\":{},",
        "\"test_case_candidates\":[]}"
    )
    .to_owned()
}

/// Build a canonical report that includes parsed behaviors.
#[must_use]
pub fn behavior_report_json(behaviors: &[Behavior]) -> String {
    let mut sorted = behaviors.to_vec();
    sorted.sort_by(|left, right| {
        left.source_path
            .cmp(&right.source_path)
            .then(left.line_number.cmp(&right.line_number))
    });
    let rows: Vec<Value> = sorted
        .iter()
        .map(|behavior| {
            json!({
                "given": behavior.given,
                "line_number": behavior.line_number,
                "source_path": behavior.source_path,
                "target_area": behavior.target_area,
                "then": behavior.then,
                "when": behavior.when,
            })
        })
        .collect();
    let report = json!({
        "bug_candidates": [],
        "duplicate_warnings": [],
        "metadata": {},
        "parsed_behaviors": rows,
        "stale_record_warnings": [],
        "summary": {},
        "test_case_candidates": [],
    });
    report.to_string()
}

/// Build a canonical report that includes bug-pattern findings.
#[must_use]
pub fn bug_report_json(findings: &[Finding]) -> String {
    let mut sorted = findings.to_vec();
    sorted.sort_by(|left, right| {
        left.source_path
            .cmp(&right.source_path)
            .then(left.line_number.cmp(&right.line_number))
            .then(left.bug_pattern_id.cmp(right.bug_pattern_id))
    });
    let rows: Vec<Value> = sorted
        .iter()
        .map(|finding| {
            json!({
                "bug_pattern_id": finding.bug_pattern_id,
                "category": finding.category,
                "citation": finding.citation,
                "confidence": finding.confidence,
                "description": finding.description,
                "evidence": finding.evidence,
                "file": finding.source_path,
                "fingerprint": finding.fingerprint,
                "line": finding.line_number,
                "line_number": finding.line_number,
                "priority_score": finding.priority_score,
                "severity": finding.severity,
                "source_path": finding.source_path,
                "suggested_fix": finding.suggested_fix,
                "title": finding.title,
            })
        })
        .collect();
    let report = json!({
        "bug_candidates": rows,
        "duplicate_warnings": [],
        "metadata": {},
        "parsed_behaviors": [],
        "stale_record_warnings": [],
        "summary": {},
        "test_case_candidates": [],
    });
    report.to_string()
}

/// Build a canonical report that turns coverage gaps into importable bug rows.
#[must_use]
pub fn coverage_report_json(gaps: &[Gap]) -> String {
    let mut sorted = gaps.to_vec();
    sorted.sort_by(|left, right| {
        left.file
            .cmp(&right.file)
            .then(left.line_start.cmp(&right.line_start))
            .then(left.kind.cmp(&right.kind))
    });
    let rows: Vec<Value> = sorted.iter().map(coverage_gap_row).collect();
    let report = json!({
        "bug_candidates": rows,
        "duplicate_warnings": [],
        "metadata": {},
        "parsed_behaviors": [],
        "stale_record_warnings": [],
        "summary": {
            "coverage_gap_count": sorted.len(),
        },
        "test_case_candidates": [],
    });
    report.to_string()
}

fn coverage_gap_row(gap: &Gap) -> Value {
    if gap.kind == "surviving_mutant" {
        return mutation_survivor_row(gap);
    }
    let title = format!(
        "Coverage gap in {}:{}-{}",
        gap.file, gap.line_start, gap.line_end
    );
    let evidence = format!(
        "{} {}:{}-{}",
        gap.kind, gap.file, gap.line_start, gap.line_end
    );
    json!({
        "bug_pattern_id": "RUSTBUG-COVERAGE-001",
        "category": "coverage_gap",
        "citation": "LCOV/Cobertura coverage report",
        "confidence": "high",
        "description": "A compiled speccheck coverage parser found code without test coverage.",
        "evidence": evidence,
        "file": gap.file,
        "fingerprint": format!("coverage:{}:{}:{}", gap.file, gap.line_start, gap.kind),
        "kind": gap.kind,
        "line": gap.line_start,
        "priority_score": coverage_priority(gap),
        "severity": coverage_severity(gap),
        "suggested_fix": "Add a focused test that exercises this line or branch, then rerun coverage.",
        "title": title,
    })
}

fn mutation_survivor_row(gap: &Gap) -> Value {
    let title = format!("Mutation survivor in {}:{}", gap.file, gap.line_start);
    let evidence = format!(
        "{} {}:{}-{}",
        gap.kind, gap.file, gap.line_start, gap.line_end
    );
    json!({
        "bug_pattern_id": "RUSTBUG-MUTATION-001",
        "category": "mutation_survivor",
        "citation": "cargo-mutants outcomes report",
        "confidence": "high",
        "description": "A compiled speccheck mutation parser found a mutant that tests did not kill.",
        "evidence": evidence,
        "file": gap.file,
        "fingerprint": format!("mutation:{}:{}:{}", gap.file, gap.line_start, gap.kind),
        "kind": gap.kind,
        "line": gap.line_start,
        "priority_score": 3.0,
        "severity": "high",
        "suggested_fix": "Kill this surviving mutant with a focused assertion, then rerun mutation testing.",
        "title": title,
    })
}

fn coverage_priority(gap: &Gap) -> f64 {
    if gap.kind == "uncovered_branch" {
        2.0
    } else {
        1.0
    }
}

fn coverage_severity(gap: &Gap) -> &'static str {
    if gap.kind == "uncovered_branch" {
        "high"
    } else {
        "medium"
    }
}
