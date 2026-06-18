"""Tests for changed-file to Bazel target mapping."""

from __future__ import annotations

from scripts import bazel_affected_targets


def test_backend_python_maps_to_python_quality() -> None:
    assert bazel_affected_targets.targets_for_paths(
        ["backend/apps/auto_issues/services/resolved_issue_index.py"]
    ) == ["//tools/quality:python"]


def test_frontend_and_rust_paths_map_to_language_targets() -> None:
    assert bazel_affected_targets.targets_for_paths(
        ["frontend/src/app/settings/settings.component.ts", "rust/Cargo.toml"]
    ) == ["//tools/quality:frontend", "//tools/quality:rust"]


def test_bazel_infrastructure_maps_to_generator_and_tag_checks() -> None:
    assert bazel_affected_targets.targets_for_paths(["tools/quality/BUILD.bazel"]) == [
        "//tools/quality:bazel_generators_test",
        "//tools/quality:bazel_target_tags_test",
    ]


def test_public_entrypoints_map_to_bazel_guard() -> None:
    assert bazel_affected_targets.targets_for_paths([".github/workflows/ci.yml"]) == [
        "//tools/quality:bazel_public_entrypoints_test"
    ]


def test_empty_paths_returns_empty_list() -> None:
    assert bazel_affected_targets.targets_for_paths(["", "   "]) == []
