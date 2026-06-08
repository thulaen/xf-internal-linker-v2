//! End-to-end CLI tests: run the built `xftool` binary over the fixtures and
//! assert the exit-code contract (0 ok / 1 findings / 2 error) and that
//! `--format json` emits parseable JSON.

use std::path::PathBuf;
use std::process::Command;

/// Absolute path to a file under `tests/fixtures/`.
fn fixture(name: &str) -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("tests/fixtures")
        .join(name)
}

/// Run `xftool <args>` and return `(exit_code, stdout)`.
fn run(args: &[&str]) -> (i32, String) {
    let output = Command::new(env!("CARGO_BIN_EXE_xftool"))
        .args(args)
        .output()
        .expect("xftool binary should run");
    let code = output.status.code().unwrap_or(-1);
    (code, String::from_utf8_lossy(&output.stdout).into_owned())
}

#[test]
fn list_prints_catalog_and_exits_zero() {
    let (code, out) = run(&["list"]);
    assert_eq!(code, 0);
    assert!(out.contains("ranking diff"));
    assert!(out.contains("store gc-report"));
}

#[test]
fn list_json_is_parseable() {
    let (code, out) = run(&["--format", "json", "list"]);
    assert_eq!(code, 0);
    let v: serde_json::Value = serde_json::from_str(&out).expect("list --format json must be JSON");
    assert!(v["rows"].as_array().unwrap().len() >= 8);
}

#[test]
fn ranking_diff_finds_changes_exit_one() {
    let a = fixture("ranking_a.json");
    let b = fixture("ranking_b.json");
    let (code, out) = run(&["ranking", "diff", a.to_str().unwrap(), b.to_str().unwrap()]);
    assert_eq!(code, 1);
    assert!(out.contains("added"));
}

#[test]
fn score_ok_breakdown_exits_zero() {
    let f = fixture("score_breakdown_ok.json");
    let (code, _) = run(&["score", "validate-breakdown", f.to_str().unwrap()]);
    assert_eq!(code, 0);
}

#[test]
fn score_bad_breakdown_exits_one() {
    let f = fixture("score_breakdown_bad.json");
    let (code, _) = run(&["score", "validate-breakdown", f.to_str().unwrap()]);
    assert_eq!(code, 1);
}

#[test]
fn index_audit_fresh_manifest_exits_zero() {
    let f = fixture("index_manifest.json");
    let (code, _) = run(&["index", "audit", f.to_str().unwrap()]);
    assert_eq!(code, 0);
}

#[test]
fn bench_summarize_parses_three_sizes() {
    let f = fixture("bench_output.txt");
    let (code, out) = run(&["bench", "summarize", f.to_str().unwrap()]);
    assert_eq!(code, 0);
    assert!(out.contains("3 benchmark"));
}

#[test]
fn weights_lint_clean_profile_exits_zero() {
    let f = fixture("weights_profile.json");
    let (code, _) = run(&["weights", "lint", f.to_str().unwrap()]);
    assert_eq!(code, 0);
}

#[test]
fn log_cluster_errors_groups_and_exits_one() {
    let f = fixture("errors.log");
    let (code, out) = run(&["log", "cluster-errors", f.to_str().unwrap()]);
    assert_eq!(code, 1);
    // 4 error lines collapse into 2 clusters (reset-by-peer + timeout).
    assert!(out.contains("4 error line(s) in 2 cluster"));
}

#[test]
fn store_gc_report_flags_orphan_exits_one() {
    let f = fixture("store_manifest.json");
    let (code, out) = run(&["store", "gc-report", f.to_str().unwrap()]);
    assert_eq!(code, 1);
    assert!(out.contains("unreferenced"));
}

#[test]
fn artifact_check_missing_artifact_is_finding_exit_one() {
    // A missing artifact is a finding (exit 1), not a usage error, when the
    // sidecar is present and declares schema + version.
    let sidecar = fixture("artifact_meta.json");
    let (code, out) = run(&[
        "artifact",
        "check",
        "/no/such/xftool-artifact.bin",
        "--sidecar",
        sidecar.to_str().unwrap(),
    ]);
    assert_eq!(code, 1);
    assert!(out.contains("failed"));
}

#[test]
fn missing_file_is_usage_error_exit_two() {
    let (code, _) = run(&["score", "validate-breakdown", "/no/such/file.json"]);
    assert_eq!(code, 2);
}
