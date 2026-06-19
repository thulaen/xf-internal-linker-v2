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


def test_push_base_falls_back_to_head_parent(monkeypatch) -> None:
    outputs = iter(
        [
            SimpleNamespace(stdout="", returncode=1),
            SimpleNamespace(stdout="parent123\n", returncode=0),
        ]
    )
    monkeypatch.setattr(commit_scope, "run_git", lambda _repo, _args: next(outputs))

    assert commit_scope.push_base(Path(".")) == "parent123"


def test_push_new_paths_use_push_base(monkeypatch) -> None:
    monkeypatch.setattr(commit_scope, "push_base", lambda _repo: "base123")
    monkeypatch.setattr(
        commit_scope,
        "run_git",
        lambda _repo, args: SimpleNamespace(stdout="new.py\n", returncode=0),
    )

    assert commit_scope.push_new_paths(Path(".")) == ["new.py"]


def test_repo_wide_scope_is_limited_to_tooling_and_global_config() -> None:
    """Only repo-wide tool and config changes request a wider check."""

    assert commit_scope.requires_full_repo_scope(["scripts/bazel_default.py"]) is True
    assert commit_scope.requires_full_repo_scope(
        ["tools/quality/internal/run-python-mutation.sh"]
    ) is False
    assert commit_scope.requires_full_repo_scope([".githooks/pre-commit"]) is True
    assert commit_scope.requires_full_repo_scope(["services/streamd/internal/state/state.go"]) is False


def test_env_paths_override_git(monkeypatch) -> None:
    """A parent hook can pass an exact file list through the environment."""

    monkeypatch.setenv("COMMIT_SCOPE_PATHS", "b.py\na.py\na.py\n")

    assert commit_scope.paths_for_mode(Path("."), "staged") == ["a.py", "b.py"]


def test_worktree_paths_collect_three_git_sources(monkeypatch) -> None:
    """Manual worktree mode keeps the old staged, unstaged, and untracked scope."""

    outputs = iter(["staged.py\n", "dirty.py\n", "new.py\n"])
    monkeypatch.setattr(
        commit_scope,
        "run_git",
        lambda _repo, _args: SimpleNamespace(stdout=next(outputs), returncode=0),
    )

    assert commit_scope.paths_for_mode(Path("."), "worktree") == [
        "dirty.py",
        "new.py",
        "staged.py",
    ]


def test_new_paths_for_each_mode(monkeypatch) -> None:
    """New-file scope matches the same staged, push, and worktree modes."""

    monkeypatch.setattr(
        commit_scope,
        "staged_new_paths",
        lambda _repo: ["staged_new.py"],
    )
    monkeypatch.setattr(
        commit_scope,
        "push_new_paths",
        lambda _repo: ["push_new.py"],
    )
    monkeypatch.setattr(
        commit_scope,
        "run_git",
        lambda _repo, _args: SimpleNamespace(stdout="worktree_new.py\n", returncode=0),
    )

    assert commit_scope.new_paths_for_mode(Path("."), "staged") == ["staged_new.py"]
    assert commit_scope.new_paths_for_mode(Path("."), "push") == ["push_new.py"]
    assert commit_scope.new_paths_for_mode(Path("."), "worktree") == ["worktree_new.py"]


def test_unknown_mode_is_rejected() -> None:
    """Unknown modes fail loudly instead of scanning the whole repo."""

    try:
        commit_scope.paths_for_mode(Path("."), "mystery")
    except ValueError as exc:
        assert "unknown commit-scope mode" in str(exc)
    else:  # pragma: no cover - assertion branch
        raise AssertionError("unknown mode should fail")


def test_main_prints_paths_and_new_paths(monkeypatch, capsys) -> None:
    """The command-line helper prints newline-separated scoped paths."""

    monkeypatch.setattr(commit_scope, "staged_paths", lambda _repo: ["a.py", "b.py"])
    monkeypatch.setattr(commit_scope, "staged_new_paths", lambda _repo: ["new.py"])

    assert commit_scope.main(["paths", "--mode", "staged"]) == 0
    assert capsys.readouterr().out == "a.py\nb.py\n"
    assert commit_scope.main(["new", "--mode", "staged"]) == 0
    assert capsys.readouterr().out == "new.py\n"


def test_main_reports_full_scope_need(monkeypatch) -> None:
    """The helper exits zero only when a wider repo check is needed."""

    monkeypatch.setattr(commit_scope, "staged_paths", lambda _repo: ["scripts/precommit-docker.sh"])
    assert commit_scope.main(["needs-full-scope", "--mode", "staged"]) == 0
    monkeypatch.setattr(commit_scope, "staged_paths", lambda _repo: ["services/streamd/go.mod"])
    assert commit_scope.main(["needs-full-scope", "--mode", "staged"]) == 1
