#!/usr/bin/env python3
"""Run Docker-only Go checks without host shell quoting."""

from __future__ import annotations

import argparse
import hashlib
import os
import shutil
import subprocess
import sys
from pathlib import Path


REPO_ROOT = Path(os.environ.get("REPO_ROOT", "/repo"))
BUILD_ROOT = Path("/tmp/xf-build/go")
REPORT_ROOT = REPO_ROOT / "backend" / "reports" / "go-quality"
IGNORED_DIRS = {".git", "vendor", "node_modules", "build", "build_tests", "dist"}
REQUIRED_TOOLS = ("go", "go-mutesting", "golangci-lint", "gosec", "gofmt")


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


def _module_report_stem(module_dir: Path) -> str:
    relative = module_dir.relative_to(REPO_ROOT).as_posix() or "root"
    digest = hashlib.sha256(relative.encode("utf-8")).hexdigest()[:12]
    safe_name = relative.replace("/", "__").replace(".", "_")
    return f"{safe_name}-{digest}"


def _module_go_files(module_dir: Path) -> list[Path]:
    files: list[Path] = []
    for current, dirs, filenames in os.walk(module_dir):
        dirs[:] = [name for name in dirs if name not in IGNORED_DIRS]
        files.extend(Path(current) / name for name in filenames if name.endswith(".go"))
    return sorted(files)


def _coverage_percent(module_dir: Path) -> float:
    report_stem = _module_report_stem(module_dir)
    cover_path = BUILD_ROOT / f"{report_stem}.cover.out"
    report_path = REPORT_ROOT / f"{report_stem}.cover.out"
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
    if not cover_path.is_file() or cover_path.stat().st_size == 0:
        raise RuntimeError(f"Go coverage report is missing: {cover_path}")
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(cover_path, report_path)
    if not report_path.is_file() or report_path.stat().st_size == 0:
        raise RuntimeError(f"Go coverage report copy is missing: {report_path}")
    result = subprocess.run(
        ["go", "tool", "cover", f"-func={cover_path}"],
        cwd=module_dir,
        text=True,
        capture_output=True,
        check=True,
    )
    for line in result.stdout.splitlines():
        if line.startswith("total:"):
            coverage = float(line.rsplit(maxsplit=1)[-1].removesuffix("%"))
            print(f"Go coverage target: 95.0%", flush=True)
            print(f"Go coverage actual: {coverage:.1f}%", flush=True)
            print(f"Go coverage module: {module_dir}", flush=True)
            print(f"Go coverage report: {report_path}", flush=True)
            print(
                "Go coverage rerun: go test -shuffle=on -race -count=1 "
                f"-coverprofile={cover_path} ./...",
                flush=True,
            )
            return coverage
    raise RuntimeError("Go coverage output did not include a total line.")


def _check_format(module_dir: Path) -> None:
    files = _module_go_files(module_dir)
    if not files:
        raise RuntimeError(f"Go module has go.mod but no .go files: {module_dir}")
    result = subprocess.run(
        ["gofmt", "-l", *[str(path.relative_to(module_dir)) for path in files]],
        cwd=module_dir,
        text=True,
        capture_output=True,
        check=True,
    )
    files = [line for line in result.stdout.splitlines() if line.endswith(".go")]
    if files:
        joined = "\n".join(files)
        raise RuntimeError(f"Go files need gofmt:\n{joined}")


def _lint_and_scan(module_dir: Path) -> None:
    _run(["golangci-lint", "run", "./..."], cwd=module_dir)
    _run(["gosec", "./..."], cwd=module_dir)


def _check_tools() -> None:
    missing = [tool for tool in REQUIRED_TOOLS if shutil.which(tool) is None]
    if missing:
        raise RuntimeError(f"Missing Go tool(s) in Docker: {', '.join(missing)}")
    _run(["go", "version"])
    _run(["go-mutesting", "--help"], check=False)
    _run(["golangci-lint", "--version"])
    _run(["gosec", "-version"])
    _run(["gofmt", "-h"], check=False)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mutation-only", action="store_true")
    args = parser.parse_args()
    BUILD_ROOT.mkdir(parents=True, exist_ok=True)
    REPORT_ROOT.mkdir(parents=True, exist_ok=True)
    _check_tools()
    modules = _go_modules()
    if not modules:
        print("No go.mod found. Go and go-mutesting are installed in Docker.")
        return 0
    for module_dir in modules:
        print(f"Checking Go module: {module_dir}")
        if not args.mutation_only:
            _check_format(module_dir)
            _lint_and_scan(module_dir)
            coverage = _coverage_percent(module_dir)
            print(f"Go coverage total: {coverage:.1f}%")
            if coverage < 95.0:
                raise RuntimeError(f"Go coverage is {coverage:.1f}%, below 95.0%.")
        _run(["go-mutesting", "./..."], cwd=module_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
