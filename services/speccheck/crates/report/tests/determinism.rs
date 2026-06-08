//! Canonical report determinism tests.

use serde_json::Value;
use speccheck_coverage::Gap;

#[test]
fn test_when_empty_report_is_built_then_keys_are_stable() {
    assert_eq!(
        speccheck_report::empty_report_json(),
        speccheck_report::empty_report_json(),
    );
}

#[test]
fn test_when_behaviors_are_unsorted_then_report_orders_by_path_and_line() {
    let behaviors = vec![
        behavior("z.md", 3),
        behavior("a.md", 2),
        behavior("a.md", 1),
    ];

    let report = speccheck_report::behavior_report_json(&behaviors);

    let first = report
        .find("\"line_number\":1")
        .expect("line 1 should exist");
    let second = report
        .find("\"line_number\":2")
        .expect("line 2 should exist");
    let third = report
        .find("\"line_number\":3")
        .expect("line 3 should exist");
    assert!(first < second);
    assert!(second < third);
}

#[test]
fn test_when_bug_findings_are_unsorted_then_report_orders_by_path_and_line() {
    let later = speccheck_detectors::find_bugs_in_source(
        "backend/apps/z/views.py",
        "def view(request):\n    return pickle.loads(request.body)\n",
    );
    let earlier = speccheck_detectors::find_bugs_in_source(
        "backend/apps/a/views.py",
        "def view(request):\n    return pickle.loads(request.body)\n",
    );
    let mut findings = Vec::new();
    findings.extend(later);
    findings.extend(earlier);

    let report = speccheck_report::bug_report_json(&findings);

    let first = report
        .find("backend/apps/a/views.py")
        .expect("first path should exist");
    let second = report
        .find("backend/apps/z/views.py")
        .expect("second path should exist");
    assert!(first < second);
    assert!(report.contains("\"bug_pattern_id\":\"RUSTBUG-SEC-002\""));
    assert!(report.contains("\"file\":\"backend/apps/a/views.py\""));
    assert!(report.contains("\"line\":2"));
    assert!(report.contains("\"title\":\"Potential security bug pattern\""));
    assert!(report.contains("\"description\":\"The detector matched a source pattern that may cause a security defect.\""));
}

#[test]
fn test_when_coverage_gaps_are_reported_then_import_fields_are_strongly_typed() {
    let report = speccheck_report::coverage_report_json(&[
        gap("apps/z.py", 40, 40, "uncovered_line"),
        gap("apps/a.py", 10, 12, "uncovered_branch"),
    ]);
    let json: Value = serde_json::from_str(&report).expect("coverage report should be JSON");
    let rows = json["bug_candidates"]
        .as_array()
        .expect("bug candidates should be an array");

    assert_eq!(json["summary"]["coverage_gap_count"], 2);
    assert_eq!(rows.len(), 2);
    assert_eq!(rows[0]["file"], "apps/a.py");
    assert_eq!(rows[0]["kind"], "uncovered_branch");
    assert_eq!(rows[0]["severity"], "high");
    assert_eq!(rows[0]["priority_score"], 2.0);
    assert_eq!(rows[0]["bug_pattern_id"], "RUSTBUG-COVERAGE-001");
    assert_eq!(rows[0]["category"], "coverage_gap");
    assert_eq!(rows[0]["line"], 10);
    assert_eq!(
        rows[0]["fingerprint"],
        "coverage:apps/a.py:10:uncovered_branch"
    );
    assert_eq!(rows[1]["severity"], "medium");
    assert_eq!(rows[1]["priority_score"], 1.0);
    assert!(rows[0]["suggested_fix"]
        .as_str()
        .unwrap_or_default()
        .contains("Add a focused test"));
}

#[test]
fn test_when_mutation_survivors_are_reported_then_import_fields_are_strongly_typed() {
    let report = speccheck_report::coverage_report_json(&[gap(
        "crates/foo/src/lib.rs",
        42,
        42,
        "surviving_mutant",
    )]);
    let json: Value = serde_json::from_str(&report).expect("mutation report should be JSON");
    let rows = json["bug_candidates"]
        .as_array()
        .expect("bug candidates should be an array");

    assert_eq!(json["summary"]["coverage_gap_count"], 1);
    assert_eq!(rows[0]["category"], "mutation_survivor");
    assert_eq!(rows[0]["kind"], "surviving_mutant");
    assert_eq!(rows[0]["severity"], "high");
    assert_eq!(rows[0]["priority_score"], 3.0);
    assert_eq!(rows[0]["bug_pattern_id"], "RUSTBUG-MUTATION-001");
    assert_eq!(
        rows[0]["fingerprint"],
        "mutation:crates/foo/src/lib.rs:42:surviving_mutant"
    );
    assert!(rows[0]["suggested_fix"]
        .as_str()
        .unwrap_or_default()
        .contains("Kill this surviving mutant"));
}

fn behavior(source_path: &str, line_number: usize) -> speccheck_parser::Behavior {
    speccheck_parser::Behavior {
        source_path: source_path.to_owned(),
        line_number,
        given: "a spec exists".to_owned(),
        when: "speccheck scans it".to_owned(),
        then: "JSON includes it".to_owned(),
        target_area: "docs".to_owned(),
    }
}

fn gap(file: &str, line_start: u32, line_end: u32, kind: &str) -> Gap {
    Gap {
        language: "python".to_owned(),
        file: file.to_owned(),
        line_start,
        line_end,
        kind: kind.to_owned(),
    }
}
