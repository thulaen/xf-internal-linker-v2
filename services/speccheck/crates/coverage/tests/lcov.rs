//! LCOV parser tests for cross-language coverage gaps.

use speccheck_coverage::{parse_lcov, Gap};

#[test]
fn parse_lcov_clusters_uncovered_lines_and_branches() {
    let report = "\
TN:
SF:apps/foo.py
DA:10,1
DA:11,0
DA:12,0
DA:14,0
BRDA:20,0,0,0
BRDA:21,0,0,-
end_of_record
";

    let gaps = parse_lcov("python", report).expect("lcov should parse");

    assert_eq!(
        gaps,
        vec![
            Gap {
                language: "python".to_string(),
                file: "apps/foo.py".to_string(),
                line_start: 11,
                line_end: 12,
                kind: "uncovered_line".to_string(),
            },
            Gap {
                language: "python".to_string(),
                file: "apps/foo.py".to_string(),
                line_start: 14,
                line_end: 14,
                kind: "uncovered_line".to_string(),
            },
            Gap {
                language: "python".to_string(),
                file: "apps/foo.py".to_string(),
                line_start: 20,
                line_end: 21,
                kind: "uncovered_branch".to_string(),
            },
        ],
    );
}

#[test]
fn parse_lcov_returns_no_gaps_for_fully_covered_records() {
    let report = "
TN:clean
SF:apps/clean.py
DA:1,3
BRDA:2,0,0,1
LF:1
end_of_record
";

    let gaps = parse_lcov("python", report).expect("clean lcov should parse");

    assert!(gaps.is_empty());
}

#[test]
fn parse_lcov_flushes_final_record_without_end_marker() {
    let report = "\
SF:apps/no-end.py
DA:3,0
";

    let gaps = parse_lcov("python", report).expect("final record should flush");

    assert_eq!(gaps[0].file, "apps/no-end.py");
    assert_eq!(gaps[0].line_start, 3);
}

#[test]
fn parse_lcov_ignores_metadata_without_splitting_a_cluster() {
    let report = "\
SF:apps/metadata.py
DA:3,0
LF:2
DA:4,0
end_of_record
";

    let gaps = parse_lcov("python", report).expect("metadata should be ignored");

    assert_eq!(gaps.len(), 1);
    assert_eq!(gaps[0].line_start, 3);
    assert_eq!(gaps[0].line_end, 4);
}

#[test]
fn parse_lcov_rejects_bad_line_numbers() {
    let err = parse_lcov("python", "SF:apps/foo.py\nDA:not-a-line,0\n")
        .expect_err("bad line number should fail");

    assert!(err.to_string().contains("DA line number"));
}

#[test]
fn parse_lcov_rejects_missing_da_comma() {
    let err =
        parse_lcov("python", "SF:apps/foo.py\nDA:7\n").expect_err("missing DA comma should fail");

    assert!(err.to_string().contains("DA record"));
}

#[test]
fn parse_lcov_rejects_malformed_branch_records() {
    let err = parse_lcov("python", "SF:apps/foo.py\nBRDA:7,0\n")
        .expect_err("short BRDA record should fail");

    assert!(err.to_string().contains("BRDA record"));
}

#[test]
fn parse_lcov_rejects_bad_branch_line_numbers() {
    let err = parse_lcov("python", "SF:apps/foo.py\nBRDA:not-a-line,0,0,0\n")
        .expect_err("bad BRDA line number should fail");

    assert!(err.to_string().contains("BRDA line number"));
}
