//! cargo-mutants survivor parser tests.

use speccheck_coverage::parse_cargo_mutants;

#[test]
fn parse_cargo_mutants_reports_missed_mutants_as_survivors() {
    let report = r#"{
        "outcomes": [
            {
                "outcome": "missed",
                "mutant": {
                    "file": "crates/foo/src/lib.rs",
                    "line": 42,
                    "description": "replace true with false"
                }
            }
        ]
    }"#;

    let gaps = parse_cargo_mutants("rust", report).expect("cargo-mutants JSON should parse");

    assert_eq!(gaps.len(), 1);
    assert_eq!(gaps[0].language, "rust");
    assert_eq!(gaps[0].file, "crates/foo/src/lib.rs");
    assert_eq!(gaps[0].line_start, 42);
    assert_eq!(gaps[0].line_end, 42);
    assert_eq!(gaps[0].kind, "surviving_mutant");
}

#[test]
fn parse_cargo_mutants_reports_timeout_mutants_as_survivors() {
    let report = r#"{
        "outcomes": [
            {
                "outcome": "timeout",
                "mutant": {
                    "span": {
                        "file": "crates/foo/src/slow.rs",
                        "start": { "line": 7 }
                    }
                }
            }
        ]
    }"#;

    let gaps = parse_cargo_mutants("rust", report).expect("nested span should parse");

    assert_eq!(gaps.len(), 1);
    assert_eq!(gaps[0].file, "crates/foo/src/slow.rs");
    assert_eq!(gaps[0].line_start, 7);
    assert_eq!(gaps[0].kind, "surviving_mutant");
}

#[test]
fn parse_cargo_mutants_sorts_and_dedupes_survivors() {
    let report = r#"{
        "outcomes": [
            { "outcome": "missed", "mutant": { "file": "crates/z/src/lib.rs", "line": 9 } },
            { "outcome": "missed", "mutant": { "file": "crates/a/src/lib.rs", "line": 20 } },
            { "outcome": "timeout", "mutant": { "file": "crates/a/src/lib.rs", "line": 20 } },
            { "outcome": "missed", "mutant": { "file": "crates/a/src/lib.rs", "line": 7 } }
        ]
    }"#;

    let gaps = parse_cargo_mutants("rust", report).expect("survivors should parse");

    assert_eq!(gaps.len(), 3);
    assert_eq!(gaps[0].file, "crates/a/src/lib.rs");
    assert_eq!(gaps[0].line_start, 7);
    assert_eq!(gaps[1].file, "crates/a/src/lib.rs");
    assert_eq!(gaps[1].line_start, 20);
    assert_eq!(gaps[2].file, "crates/z/src/lib.rs");
    assert_eq!(gaps[2].line_start, 9);
}

#[test]
fn parse_cargo_mutants_reads_file_and_line_from_nested_arrays() {
    let report = r#"{
        "outcomes": [
            {
                "status": "missed",
                "mutant": {
                    "locations": [
                        { "file": "crates/array/src/lib.rs" },
                        { "line": 17 }
                    ]
                }
            }
        ]
    }"#;

    let gaps = parse_cargo_mutants("rust", report).expect("nested arrays should parse");

    assert_eq!(gaps.len(), 1);
    assert_eq!(gaps[0].file, "crates/array/src/lib.rs");
    assert_eq!(gaps[0].line_start, 17);
}

#[test]
fn parse_cargo_mutants_ignores_caught_and_unviable_mutants() {
    let report = r#"{
        "outcomes": [
            { "outcome": "caught", "mutant": { "file": "src/lib.rs", "line": 1 } },
            { "outcome": "unviable", "mutant": { "file": "src/lib.rs", "line": 2 } }
        ]
    }"#;

    let gaps = parse_cargo_mutants("rust", report).expect("non-survivors should parse");

    assert!(gaps.is_empty());
}

#[test]
fn parse_cargo_mutants_rejects_invalid_json() {
    let error = parse_cargo_mutants("rust", "{not-json").expect_err("bad JSON should fail");

    assert!(error.to_string().contains("cargo-mutants JSON is invalid"));
}

#[test]
fn parse_cargo_mutants_rejects_survivor_without_file() {
    let report = r#"{
        "outcomes": [
            { "outcome": "missed", "mutant": { "line": 12 } }
        ]
    }"#;

    let error = parse_cargo_mutants("rust", report).expect_err("missing file should fail");

    assert!(error
        .to_string()
        .contains("cargo-mutants survivor is missing file"));
}

#[test]
fn parse_cargo_mutants_rejects_survivor_without_line() {
    let report = r#"{
        "outcomes": [
            { "outcome": "missed", "mutant": { "file": "src/lib.rs" } }
        ]
    }"#;

    let error = parse_cargo_mutants("rust", report).expect_err("missing line should fail");

    assert!(error
        .to_string()
        .contains("cargo-mutants survivor is missing line"));
}
