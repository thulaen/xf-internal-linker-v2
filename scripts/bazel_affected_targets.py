#!/usr/bin/env python3
"""Map changed repository paths to Bazel quality targets."""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path

try:
    from scripts.inter_model_interface import normalize_path as normalise_path
except ModuleNotFoundError:  # pragma: no cover - direct script execution path.
    from inter_model_interface import normalize_path as normalise_path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TARGET = "//tools/quality:all"


def targets_for_paths(paths: Iterable[str]) -> list[str]:
    """Return stable Bazel targets that cover the supplied paths."""
    targets: set[str] = set()
    for raw_path in paths:
        path = normalise_path(raw_path)
        if not path:
            continue
        targets.update(_targets_for_path(path))
    return sorted(targets)


_PREFIX_RULES: list[tuple[tuple[str, ...], set[str], str | None]] = [
    # (path prefixes, targets to add, required suffix or None for any file)
    (
        ("backend/", "scripts/", ".githooks/"),
        {"//tools/quality:python", "//tools/quality:mutation"},
        ".py",
    ),
    (
        ("frontend/",),
        {"//tools/quality:frontend"},
        None,
    ),
    (
        ("frontend/src/app/",),
        {"//tools/quality:mutation"},
        None,
    ),
    (
        ("rust/", "services/speccheck/"),
        {"//tools/quality:rust", "//tools/quality:mutation"},
        None,
    ),
]

_EXACT_RULES: dict[str, set[str]] = {
    "Cargo.toml": {"//tools/quality:rust", "//tools/quality:mutation"},
    "Cargo.lock": {"//tools/quality:rust", "//tools/quality:mutation"},
    "rust-toolchain.toml": {"//tools/quality:rust", "//tools/quality:mutation"},
    "scripts/run-tool-readiness.sh": {"//tools/quality:tool_readiness"},
    "tools/quality/tool_readiness.sh": {"//tools/quality:tool_readiness"},
    "scripts/run-pbt.sh": {"//tools/quality:pbt"},
    "tools/quality/pbt.sh": {"//tools/quality:pbt"},
}

_BAZEL_INFRA_TARGETS = {
    "//tools/quality:bazel_generators_test",
    "//tools/quality:bazel_target_tags_test",
    "//tools/quality:mutation",
}


def _targets_for_path(path: str) -> set[str]:
    targets: set[str] = set()
    for prefixes, rule_targets, suffix in _PREFIX_RULES:
        if path.startswith(prefixes) and (suffix is None or path.endswith(suffix)):
            targets.update(rule_targets)
    if path in _EXACT_RULES:
        targets.update(_EXACT_RULES[path])
    if _is_bazel_infrastructure(path):
        targets.update(_BAZEL_INFRA_TARGETS)
    if _is_public_entrypoint(path):
        targets.add("//tools/quality:bazel_public_entrypoints_test")
    return targets


def _is_bazel_infrastructure(path: str) -> bool:
    return (
        path.endswith("BUILD.bazel")
        or path in {"MODULE.bazel", ".bazelrc", ".bazelversion"}
        or path.startswith("tools/quality/")
        or path.startswith("tools/runners/")
        or path.startswith("scripts/gen_bazel_")
        or path == "scripts/lib/bazel_gen.py"
    )


def _is_public_entrypoint(path: str) -> bool:
    return path in {
        "scripts/precommit-docker.sh",
        "scripts/prepush-docker.sh",
        "scripts/verify.ps1",
        "scripts/hook_orchestrator.py",
        ".github/workflows/ci.yml",
        ".github/workflows/ci-language-quality.yml",
        ".github/workflows/scoped-mutation.yml",
        "AGENTS.md",
        "docs/BAZEL-MIGRATION-PLAN.md",
        "docs/CODE-COVERAGE-RULES.md",
        "docs/KUBE-PLAN-STATUS.md",
    }


def changed_paths(mode: str) -> list[str]:
    """Read changed paths from the repo commit-scope helper."""
    result = subprocess.run(
        [sys.executable, "scripts/commit_scope.py", "paths", "--mode", mode],
        cwd=REPO_ROOT,
        text=True,
        capture_output=True,
        check=False,
        timeout=30,
    )
    return result.stdout.splitlines()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("paths", nargs="*", help="Repo-relative paths to map.")
    parser.add_argument("--changed", action="store_true", help="Use changed worktree paths.")
    parser.add_argument(
        "--mode",
        choices=("staged", "push", "worktree"),
        default="worktree",
        help="Commit-scope mode used with --changed.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = changed_paths(args.mode) if args.changed else args.paths
    targets = targets_for_paths(paths)
    print("\n".join(targets))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
