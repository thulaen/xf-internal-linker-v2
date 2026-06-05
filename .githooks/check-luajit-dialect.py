#!/usr/bin/env python
"""Run LuaJIT 2.1 syntax checks and block newer Lua dialect syntax."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]
LUA_ROOTS = (
    "apps",
    "frontend/nginx-lua",
    ".githooks/lua",
    "services",
)
FORBIDDEN_PATTERNS = {
    "Lua 5.3 integer division": re.compile(r"(?<![:./])//"),
    "Lua 5.3 bitwise operator": re.compile(r"(?<![\w])(?:~|<<|>>|&)(?![\w])"),
    "Lua 5.4 close attribute": re.compile(r"<\s*close\s*>"),
    "Lua 5.3 utf8 library": re.compile(r"(?<![\w.])utf8\s*\."),
}


def _candidates(all_files: bool, paths: list[str]) -> list[Path]:
    if paths:
        return [ROOT / line for line in paths if line.endswith(".lua") and (ROOT / line).exists()]
    if all_files:
        files: list[Path] = []
        for root in LUA_ROOTS:
            path = ROOT / root
            if path.exists():
                files.extend(path.rglob("*.lua"))
        return files
    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in completed.stdout.splitlines() if line.endswith(".lua")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    failed = False
    for path in _candidates(args.all, args.paths):
        text = path.read_text(encoding="utf-8")
        for reason, pattern in FORBIDDEN_PATTERNS.items():
            if pattern.search(text):
                print(f"{path.relative_to(ROOT)} uses forbidden dialect feature: {reason}", file=sys.stderr)
                failed = True
        try:
            subprocess.run(["luajit", "-bl", str(path)], cwd=ROOT, check=True, capture_output=True, text=True)
        except FileNotFoundError:
            print("luajit -bl unavailable; install LuaJIT 2.1 before committing Lua files", file=sys.stderr)
            failed = True
            break
        except subprocess.CalledProcessError as exc:
            print(exc.stderr, file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
