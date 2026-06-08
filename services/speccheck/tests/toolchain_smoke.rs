//! Workspace-level Rust toolchain smoke test.

#[test]
fn test_when_workspace_tests_run_then_smoke_passes() {
    assert_eq!(2 + 2, 4);
}
