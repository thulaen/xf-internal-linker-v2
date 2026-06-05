#!/usr/bin/env python
"""Block Lua scripts that bypass the capability sandbox."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
FORBIDDEN = {
    "io": re.compile(r"(?<![\w.])io\s*\."),
    "os": re.compile(r"(?<![\w.])os\s*\."),
    "debug": re.compile(r"(?<![\w.])debug\s*\."),
    "require": re.compile(r"(?<![\w.])require\s*\("),
    "loadfile": re.compile(r"(?<![\w.])loadfile\s*\("),
    "dofile": re.compile(r"(?<![\w.])dofile\s*\("),
}
LUA_ROOTS = (
    "apps",
    "frontend/nginx-lua",
    ".githooks/lua",
    "services",
)


def _staged_lua_files() -> list[Path]:
    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in completed.stdout.splitlines() if line.endswith(".lua")]


def _all_lua_files() -> list[Path]:
    files: list[Path] = []
    for root in LUA_ROOTS:
        path = ROOT / root
        if path.exists():
            files.extend(path.rglob("*.lua"))
    return files


def _explicit_lua_files(paths: list[str]) -> list[Path]:
    return [ROOT / path for path in paths if path.endswith(".lua") and (ROOT / path).exists()]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    failed = False
    candidates = _explicit_lua_files(args.paths) if args.paths else (
        _all_lua_files() if args.all else _staged_lua_files()
    )
    for path in candidates:
        text = path.read_text(encoding="utf-8")
        for name, pattern in FORBIDDEN.items():
            if pattern.search(text):
                print(f"LuaSandboxViolationError: {path.relative_to(ROOT)} uses {name}", file=sys.stderr)
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
