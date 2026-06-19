"""Tests for changed-file to Bazel target mapping."""

from __future__ import annotations

from scripts import bazel_affected_targets
from types import SimpleNamespace


def test_backend_python_maps_to_python_quality() -> None:
    assert bazel_affected_targets.targets_for_paths(
        ["backend/apps/auto_issues/services/resolved_issue_index.py"]
    ) == ["//tools/quality:mutation", "//tools/quality:python"]


def test_githook_python_maps_to_python_quality() -> None:
    assert bazel_affected_targets.targets_for_paths(
        [".githooks/check-bazel-public-entrypoints.py"]
    ) == [
        "//tools/quality:mutation",
        "//tools/quality:python",
    ]


def test_frontend_and_rust_paths_map_to_language_targets() -> None:
    assert bazel_affected_targets.targets_for_paths(
        ["frontend/src/app/settings/settings.component.ts", "rust/Cargo.toml"]
    ) == ["//tools/quality:frontend", "//tools/quality:mutation", "//tools/quality:rust"]


def test_bazel_infrastructure_maps_to_generator_and_tag_checks() -> None:
    assert bazel_affected_targets.targets_for_paths(["tools/quality/BUILD.bazel"]) == [
        "//tools/quality:bazel_generators_test",
        "//tools/quality:bazel_target_tags_test",
        "//tools/quality:mutation",
    ]


def test_public_entrypoints_map_to_bazel_guard() -> None:
    assert bazel_affected_targets.targets_for_paths([".github/workflows/ci.yml"]) == [
        "//tools/quality:bazel_public_entrypoints_test"
    ]


def test_tool_readiness_and_property_tests_have_bazel_targets() -> None:
    assert bazel_affected_targets.targets_for_paths(
        ["scripts/run-tool-readiness.sh", "scripts/run-pbt.sh"]
    ) == ["//tools/quality:pbt", "//tools/quality:tool_readiness"]


def test_empty_paths_returns_empty_list() -> None:
    assert bazel_affected_targets.targets_for_paths(["", "   "]) == []


def test_changed_paths_uses_requested_mode(monkeypatch) -> None:
    captured = {}

    def fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return SimpleNamespace(stdout="backend/apps/demo.py\n")

    monkeypatch.setattr(bazel_affected_targets.subprocess, "run", fake_run)

    assert bazel_affected_targets.changed_paths("push") == ["backend/apps/demo.py"]
    assert "--mode" in captured["cmd"]
    assert "push" in captured["cmd"]


def test_main_prints_changed_targets(monkeypatch, capsys) -> None:
    monkeypatch.setattr(
        bazel_affected_targets,
        "changed_paths",
        lambda mode: ["frontend/src/app/demo.service.ts"],
    )

    assert bazel_affected_targets.main(["--changed", "--mode", "staged"]) == 0
    output = capsys.readouterr().out
    assert "//tools/quality:frontend" in output
    assert "//tools/quality:mutation" in output
