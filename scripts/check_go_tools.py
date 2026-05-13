#!/usr/bin/env python3
"""Run Docker-only Go checks without host shell quoting."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/repo"))
BUILD_ROOT = Path("/tmp/xf-build/go")
IGNORED_DIRS = {".git", "vendor", "node_modules", "build", "build_tests", "dist"}


def _run(command: list[str], cwd: Path | None = None, check: bool = True) -> subprocess.CompletedProcess[str]:
    print("+ " + " ".join(command), flush=True)
    return subprocess.run(command, cwd=cwd, text=True, capture_output=False, check=check)


def _go_modules() -> list[Path]:
    modules: list[Path] = []
    for current, dirs, filenames in os.walk(REPO_ROOT):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        if "go.mod" in filenames:
            modules.append(Path(current))
    return sorted(modules)


def _coverage_percent(module_dir: Path) -> float:
    cover_path = BUILD_ROOT / f"{module_dir.name or 'root'}-cover.out"
    _run(
        [
            "go",
            "test",
            "-shuffle=on",
            "-race",
            "-count=1",
            f"-coverprofile={cover_path}",
            "./...",
        ],
        cwd=module_dir,
    )
    result = subprocess.run(
        ["go", "tool", "cover", f"-func={cover_path}"],
        cwd=module_dir,
        text=True,
        capture_output=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("total:"):
            return float(line.rsplit(maxsplit=1)[-1].removesuffix("%"))
    raise RuntimeError("Go coverage output did not include a total line.")


def _check_tools() -> None:
    _run(["go", "version"])
    _run(["go-mutesting", "--help"], check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutation-only", action="store_true")
    args = parser.parse_args()
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    _check_tools()
    modules = _go_modules()
    if not modules:
        print("No go.mod found. Go and go-mutesting are installed in Docker.")
        return 0
    for module_dir in modules:
        print(f"Checking Go module: {module_dir}")
        if not args.mutation_only:
            coverage = _coverage_percent(module_dir)
            print(f"Go coverage total: {coverage:.1f}%")
            if coverage < 95.0:
                raise RuntimeError(f"Go coverage is {coverage:.1f}%, below 95.0%.")
        _run(["go-mutesting", "./..."], cwd=module_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
