//! CLI output smoke tests.

use std::process::Command;

#[test]
fn test_when_cli_runs_then_stdout_is_canonical_json() {
    let binary = env!("CARGO_BIN_EXE_speccheck");
    let output = Command::new(binary).output().expect("speccheck should run");

    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).is_empty());
    assert_eq!(
        String::from_utf8_lossy(&output.stdout).trim(),
        speccheck_report::empty_report_json()
    );
}

#[test]
fn test_when_scan_reads_behavior_file_then_stdout_contains_parsed_behavior() {
    let fixture = std::env::temp_dir().join(format!("speccheck-scan-{}.md", std::process::id()));
    std::fs::write(
        &fixture,
        "Given a spec exists\nWhen speccheck scans it\nThen JSON includes it",
    )
    .expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("scan")
        .arg(&fixture)
        .output()
        .expect("speccheck scan should run");

    let _ = std::fs::remove_file(&fixture);
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).is_empty());
    assert!(stdout.contains("\"parsed_behaviors\":[{"));
    assert!(stdout.contains("\"given\":\"a spec exists\""));
    assert!(stdout.contains("\"when\":\"speccheck scans it\""));
    assert!(stdout.contains("\"then\":\"JSON includes it\""));
}

#[test]
fn test_when_find_bugs_reads_pickle_loads_then_stdout_contains_security_finding() {
    let fixture =
        std::env::temp_dir().join(format!("speccheck-find-bugs-{}.py", std::process::id()));
    std::fs::write(
        &fixture,
        "def view(request):\n    return pickle.loads(request.body)\n",
    )
    .expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("find-bugs")
        .arg(&fixture)
        .output()
        .expect("speccheck find-bugs should run");

    let _ = std::fs::remove_file(&fixture);
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).is_empty());
    assert!(stdout.contains("\"bug_pattern_id\":\"RUSTBUG-SEC-002\""));
    assert!(stdout.contains("\"severity\":\"critical\""));
}

#[test]
fn test_when_coverage_gaps_reads_lcov_then_stdout_contains_importable_bug_candidate() {
    let fixture = std::env::temp_dir().join(format!("speccheck-lcov-{}.info", std::process::id()));
    std::fs::write(
        &fixture,
        "SF:apps/foo.py\nDA:11,0\nBRDA:20,0,0,0\nend_of_record\n",
    )
    .expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("coverage-gaps")
        .arg("--format")
        .arg("lcov")
        .arg(&fixture)
        .output()
        .expect("speccheck coverage-gaps should run");

    let _ = std::fs::remove_file(&fixture);
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).is_empty());
    assert!(stdout.contains("\"bug_pattern_id\":\"RUSTBUG-COVERAGE-001\""));
    assert!(stdout.contains("\"category\":\"coverage_gap\""));
    assert!(stdout.contains("\"file\":\"apps/foo.py\""));
    assert!(stdout.contains("\"kind\":\"uncovered_line\""));
}

#[test]
fn test_when_coverage_gaps_has_stub_dir_then_binary_writes_bdd_stub() {
    let fixture =
        std::env::temp_dir().join(format!("speccheck-lcov-stub-{}.info", std::process::id()));
    let stub_dir = std::env::temp_dir().join(format!("speccheck-stubs-{}", std::process::id()));
    std::fs::create_dir_all(&stub_dir).expect("stub directory should be writable");
    std::fs::write(
        &fixture,
        "SF:apps/foo/services/bar.py\nDA:42,0\nend_of_record\n",
    )
    .expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("coverage-gaps")
        .arg("--format")
        .arg("lcov")
        .arg("--stubs-dir")
        .arg(&stub_dir)
        .arg(&fixture)
        .output()
        .expect("speccheck coverage-gaps should run");

    let stub_path = stub_dir.join("apps_foo_services_bar_42.py");
    let stub = std::fs::read_to_string(&stub_path).expect("stub should be written");
    let _ = std::fs::remove_file(&fixture);
    let _ = std::fs::remove_file(stub_path);
    let _ = std::fs::remove_dir(&stub_dir);
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).is_empty());
    assert!(stub.contains("AUTO-GENERATED-STUB"));
    assert!(stub.contains("Given coverage is missing for apps/foo/services/bar.py:42"));
    assert!(stub.contains("When the affected behavior is exercised"));
    assert!(stub.contains("Then this gap should be covered by a real assertion"));
    assert!(stub.contains("def test_when_bar_line_42_then_gap_is_covered():"));
}

#[test]
fn test_when_coverage_gaps_reads_cobertura_then_stdout_contains_importable_bug_candidate() {
    let fixture =
        std::env::temp_dir().join(format!("speccheck-cobertura-{}.xml", std::process::id()));
    std::fs::write(
        &fixture,
        r#"<class filename="apps/foo.py"><line number="21" hits="1" branch="true" condition-coverage="50% (1/2)"/></class>"#,
    )
    .expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("coverage-gaps")
        .arg("--format")
        .arg("cobertura")
        .arg(&fixture)
        .output()
        .expect("speccheck coverage-gaps should run");

    let _ = std::fs::remove_file(&fixture);
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).is_empty());
    assert!(stdout.contains("\"bug_pattern_id\":\"RUSTBUG-COVERAGE-001\""));
    assert!(stdout.contains("\"kind\":\"uncovered_branch\""));
}

#[test]
fn test_when_coverage_gaps_reads_cargo_mutants_then_stdout_contains_mutation_survivor() {
    let fixture =
        std::env::temp_dir().join(format!("speccheck-cli-mutants-{}.json", std::process::id()));
    std::fs::write(
        &fixture,
        r#"{"outcomes":[{"outcome":"missed","mutant":{"file":"crates/foo/src/lib.rs","line":42}}]}"#,
    )
    .expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("coverage-gaps")
        .arg("--format")
        .arg("cargo-mutants")
        .arg(&fixture)
        .output()
        .expect("speccheck coverage-gaps should run");

    let _ = std::fs::remove_file(&fixture);
    let stdout = String::from_utf8_lossy(&output.stdout);
    assert!(
        output.status.success(),
        "stderr was {}",
        String::from_utf8_lossy(&output.stderr)
    );
    assert!(String::from_utf8_lossy(&output.stderr).is_empty());
    assert!(stdout.contains("\"bug_pattern_id\":\"RUSTBUG-MUTATION-001\""));
    assert!(stdout.contains("\"category\":\"mutation_survivor\""));
    assert!(stdout.contains("\"kind\":\"surviving_mutant\""));
    assert!(stdout.contains("\"line\":42"));
}

#[test]
fn test_when_coverage_gaps_input_is_malformed_then_cli_fails_plainly() {
    let fixture = std::env::temp_dir().join(format!(
        "speccheck-bad-cobertura-{}.xml",
        std::process::id()
    ));
    std::fs::write(&fixture, r#"<line number="1" hits="0"/>"#).expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("coverage-gaps")
        .arg("--format")
        .arg("cobertura")
        .arg(&fixture)
        .output()
        .expect("speccheck coverage-gaps should run");

    let _ = std::fs::remove_file(&fixture);
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("could not parse"));
}

#[test]
fn test_when_unknown_command_is_used_then_cli_fails_in_plain_english() {
    let fixture = std::env::temp_dir().join(format!("speccheck-unknown-{}.md", std::process::id()));
    std::fs::write(&fixture, "Given a spec\nWhen it runs\nThen it passes")
        .expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("bogus")
        .arg(&fixture)
        .output()
        .expect("speccheck should run");

    let _ = std::fs::remove_file(&fixture);
    assert!(!output.status.success());
    assert!(String::from_utf8_lossy(&output.stderr).contains("unknown command `bogus`"));
}

#[test]
fn test_when_scan_input_is_invalid_then_cli_reports_line_number() {
    let fixture = std::env::temp_dir().join(format!("speccheck-invalid-{}.md", std::process::id()));
    std::fs::write(&fixture, "# Heading\n\nGiven a spec\nWhen it runs")
        .expect("fixture should be writable");
    let binary = env!("CARGO_BIN_EXE_speccheck");

    let output = Command::new(binary)
        .arg("scan")
        .arg(&fixture)
        .output()
        .expect("speccheck scan should run");

    let _ = std::fs::remove_file(&fixture);
    let stderr = String::from_utf8_lossy(&output.stderr);
    assert!(!output.status.success());
    assert!(stderr.contains(":3 Given must be followed by exactly one When and one Then line."));
}
