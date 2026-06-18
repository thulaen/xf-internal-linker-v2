"""Map changed files to existing Bazel targets."""

from __future__ import annotations

import argparse
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def targets_for_paths(paths: list[str]) -> list[str]:
    """Return sorted Bazel targets that are already present in the repo."""
    targets: set[str] = set()
    for raw_path in paths:
        path = raw_path.replace("\\", "/").strip()
        if not path:
            continue
        target = _target_for_path(path)
        if target:
            targets.add(target)
    return sorted(targets)


def changed_files() -> list[str]:
    completed = subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [line.strip() for line in completed.stdout.splitlines() if line.strip()]


def _target_for_path(path: str) -> str:
    if path.startswith("frontend/") and (ROOT / "frontend" / "BUILD.bazel").exists():
        return "//frontend:runner_toolbox"
    if path.startswith("tools/runners/"):
        return "//tools/runners/..."
    if path.startswith("tools/preflight/") and (ROOT / "tools/preflight/BUILD.bazel").exists():
        return "//tools/preflight:all"
    return ""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Print Bazel targets for changed files.")
    parser.add_argument("paths", nargs="*", help="Optional explicit changed paths.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    paths = args.paths or changed_files()
    for target in targets_for_paths(paths):
        print(target)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
