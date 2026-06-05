#!/usr/bin/env python
"""Require Lua tests that mutate shared mocks to reset them with after_each.

Scans staged or full-tree *_spec.lua files, which are still *.lua files.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


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
        mutates_mock = "xf.test.mock_capability" in text or "ngx_mock" in text or "redis_mock" in text
        if mutates_mock and "after_each" not in text:
            print(f"{path.relative_to(ROOT)} mutates a shared mock without after_each reset", file=sys.stderr)
            failed = True
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
