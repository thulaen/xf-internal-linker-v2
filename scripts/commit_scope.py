#!/usr/bin/env python3
"""Shared file-scope helper for commit and push quality tools."""

from __future__ import annotations

import argparse
import os
import subprocess
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

FULL_SCOPE_PREFIXES = (
    ".githooks/",
    ".github/workflows/",
)
FULL_SCOPE_EXACT = {
    "docker-compose.yml",
    "pyproject.toml",
    "backend/pytest.ini",
    "frontend/angular.json",
    "frontend/karma.conf.js",
    "frontend/package.json",
    "frontend/package-lock.json",
    "scripts/commit_scope.py",
    "scripts/precommit-docker.sh",
    "scripts/prepush-docker.sh",
    "scripts/run-angular-quality.sh",
    "scripts/run-cpp-quality.sh",
    "scripts/run-go-quality.sh",
    "scripts/run-haskell-quality.sh",
    "scripts/run-mint-quality-shard.sh",
    "scripts/run-python-quality.sh",
    "scripts/run-quality-debt-report.sh",
    "scripts/run-rust-quality.sh",
    "scripts/run-scoped-static-quality.ps1",
    "scripts/plan-scoped-quality-shards.py",
    "scripts/tdd_write_guard.py",
    "scripts/icecc_helper.sh",
}

GENERATED_SCOPE_PREFIXES = (
    ".tmp/",
    "backend/.mutmut-cache/",
    "frontend/.stryker-tmp/",
    "reports/lua/",
    "reports/mutation/",
    "services/findbugs-haskell/dist-newstyle/",
    "services/sidecars/api/gen/",
    "services/speccheck/mutants.out/",
    "services/speccheck/mutants.out.old/",
    "tmp/free-code-review/",
)

GENERATED_SCOPE_SUFFIXES = (
    ".tmp",
)

GENERATED_SCOPE_EXACT = {
    ".tmp",
    "backend/.mutmut-cache",
    "frontend/.stryker-tmp",
    "luacov.stats.out",
    "services/sidecars/sidecars",
    "services/speccheck/mutants.out",
    "services/speccheck/mutants.out.old",
    "tmp/free-code-review",
}


def run_git(repo_root: Path, args: tuple[str, ...]) -> subprocess.CompletedProcess[str]:
    """Run Git and return captured text output."""
    return subprocess.run(
        ["git", *args],
        cwd=repo_root,
        text=True,
        capture_output=True,
        check=False,
    )


def normalize_paths(lines: str) -> list[str]:
    """Return stable repo-relative paths."""
    paths = {
        line.strip().replace("\\", "/")
        for line in lines.splitlines()
        if line.strip()
    }
    paths = {
        path
        for path in paths
        if path not in GENERATED_SCOPE_EXACT
        and not path.startswith(GENERATED_SCOPE_PREFIXES)
        and not path.endswith(GENERATED_SCOPE_SUFFIXES)
    }
    return sorted(paths)


def staged_paths(repo_root: Path) -> list[str]:
    """Return files staged for this commit."""
    result = run_git(repo_root, ("diff", "--cached", "--name-only", "--diff-filter=ACM"))
    return normalize_paths(result.stdout)


def staged_new_paths(repo_root: Path) -> list[str]:
    """Return files newly staged for this commit."""
    result = run_git(repo_root, ("diff", "--cached", "--name-only", "--diff-filter=A"))
    return normalize_paths(result.stdout)


def push_base(repo_root: Path) -> str:
    """Return the base commit for files about to be pushed."""
    upstream = run_git(repo_root, ("rev-parse", "--abbrev-ref", "--symbolic-full-name", "@{upstream}"))
    if upstream.returncode == 0 and upstream.stdout.strip():
        base = run_git(repo_root, ("merge-base", "HEAD", upstream.stdout.strip()))
        if base.returncode == 0 and base.stdout.strip():
            return base.stdout.strip()
    fallback = run_git(repo_root, ("rev-parse", "HEAD~1"))
    return fallback.stdout.strip() if fallback.returncode == 0 else "HEAD"


def push_paths(repo_root: Path) -> list[str]:
    """Return files changed by commits that have not reached upstream yet."""
    base = push_base(repo_root)
    result = run_git(repo_root, ("diff", "--name-only", "--diff-filter=ACM", f"{base}..HEAD"))
    return normalize_paths(result.stdout)


def push_new_paths(repo_root: Path) -> list[str]:
    """Return new files changed by commits that have not reached upstream yet."""
    base = push_base(repo_root)
    result = run_git(repo_root, ("diff", "--name-only", "--diff-filter=A", f"{base}..HEAD"))
    return normalize_paths(result.stdout)


def worktree_paths(repo_root: Path) -> list[str]:
    """Return the old manual-check scope: staged, unstaged, and untracked files."""
    commands = (
        ("diff", "--cached", "--name-only", "--diff-filter=ACM"),
        ("diff", "--name-only", "--diff-filter=ACM", "HEAD"),
        ("ls-files", "--others", "--exclude-standard"),
    )
    output = "\n".join(run_git(repo_root, command).stdout for command in commands)
    return normalize_paths(output)


def paths_from_env() -> list[str]:
    """Return explicit scoped paths passed by a caller, if present."""
    value = os.environ.get("COMMIT_SCOPE_PATHS", "")
    return normalize_paths(value)


def paths_for_mode(repo_root: Path, mode: str) -> list[str]:
    """Return repo paths for the requested quality-tool scope."""
    env_paths = paths_from_env()
    if env_paths:
        return env_paths
    if mode == "staged":
        return staged_paths(repo_root)
    if mode == "push":
        return push_paths(repo_root)
    if mode == "worktree":
        return worktree_paths(repo_root)
    raise ValueError(f"unknown commit-scope mode: {mode}")


def new_paths_for_mode(repo_root: Path, mode: str) -> list[str]:
    """Return new repo paths for the requested quality-tool scope."""
    if mode == "staged":
        return staged_new_paths(repo_root)
    if mode == "push":
        return push_new_paths(repo_root)
    if mode == "worktree":
        commands = (
            ("diff", "--cached", "--name-only", "--diff-filter=A"),
            ("diff", "--name-only", "--diff-filter=A", "HEAD"),
            ("ls-files", "--others", "--exclude-standard"),
        )
        output = "\n".join(run_git(repo_root, command).stdout for command in commands)
        return normalize_paths(output)
    raise ValueError(f"unknown commit-scope mode: {mode}")


def requires_full_repo_scope(paths: list[str]) -> bool:
    """Return true when a staged tool or global config change needs a wider check."""
    return any(path in FULL_SCOPE_EXACT or path.startswith(FULL_SCOPE_PREFIXES) for path in paths)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line options."""
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=("paths", "new", "needs-full-scope"))
    parser.add_argument("--mode", choices=("staged", "push", "worktree"), default="staged")
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Print scoped paths or return whether full scope is required."""
    args = parse_args(argv)
    repo_root = args.repo_root.resolve()
    paths = paths_for_mode(repo_root, args.mode)
    if args.command == "new":
        paths = new_paths_for_mode(repo_root, args.mode)
    if args.command == "needs-full-scope":
        return 0 if requires_full_repo_scope(paths) else 1
    print("\n".join(paths))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
