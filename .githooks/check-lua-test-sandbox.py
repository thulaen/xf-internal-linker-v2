#!/usr/bin/env python
"""Block Lua test files that call forbidden libraries directly.

Scans staged or full-tree *_spec.lua files, which are still *.lua files.
"""

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
}


def _candidates(all_files: bool, paths: list[str]) -> list[Path]:
    if paths:
        return [ROOT / line for line in paths if line.endswith("_spec.lua") and (ROOT / line).exists()]
    if all_files:
        return [p for p in ROOT.rglob("*_spec.lua") if "node_modules" not in p.parts]
    completed = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
    )
    return [ROOT / line for line in completed.stdout.splitlines() if line.endswith("_spec.lua")]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--all", action="store_true")
    parser.add_argument("paths", nargs="*")
    args = parser.parse_args()
    failed = False
    for path in _candidates(args.all, args.paths):
        text = path.read_text(encoding="utf-8")
        for name, pattern in FORBIDDEN.items():
            if pattern.search(text):
                print(f"LuaSandboxViolationError: {path.relative_to(ROOT)} uses {name}", file=sys.stderr)
                failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
