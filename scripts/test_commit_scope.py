"""Tests for commit-scoped quality-tool inputs."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent))
import commit_scope


def test_staged_paths_are_normalized_and_sorted(monkeypatch) -> None:
    """Staged paths are the default source for commit tools."""

    def fake_run(_repo_root: Path, args: tuple[str, ...]):
        assert args == ("diff", "--cached", "--name-only", "--diff-filter=ACM")
        return SimpleNamespace(stdout="scripts\\b.py\nscripts/a.py\nscripts/a.py\n", returncode=0)

    monkeypatch.setattr(commit_scope, "run_git", fake_run)

    assert commit_scope.paths_for_mode(Path("."), "staged") == ["scripts/a.py", "scripts/b.py"]


def test_push_paths_use_upstream_merge_base(monkeypatch) -> None:
    """Push checks use only files in commits that are about to be pushed."""

    calls: list[tuple[str, ...]] = []

    def fake_run(_repo_root: Path, args: tuple[str, ...]):
        calls.append(args)
        if args == ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"):
            return SimpleNamespace(stdout="origin/master\n", returncode=0)
        if args == ("merge-base", "HEAD", "origin/master"):
            return SimpleNamespace(stdout="abc123\n", returncode=0)
        return SimpleNamespace(stdout="services/streamd/go.mod\n", returncode=0)

    monkeypatch.setattr(commit_scope, "run_git", fake_run)

    assert commit_scope.paths_for_mode(Path("."), "push") == ["services/streamd/go.mod"]
    assert ("diff", "--name-only", "--diff-filter=ACM", "abc123..HEAD") in calls


def test_repo_wide_scope_is_limited_to_tooling_and_global_config() -> None:
    """Only repo-wide tool and config changes request a wider check."""

    assert commit_scope.requires_full_repo_scope(["scripts/run-python-quality.sh"]) is True
    assert commit_scope.requires_full_repo_scope([".githooks/pre-commit"]) is True
    assert commit_scope.requires_full_repo_scope(["services/streamd/internal/state/state.go"]) is False
