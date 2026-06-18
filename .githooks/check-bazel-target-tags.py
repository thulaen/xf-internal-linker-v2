#!/usr/bin/env python3
"""Check Bazel test targets carry a shard tag."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_TARGET_RE = re.compile(r"^\s*(py_test|js_test|rust_test|sh_test)\(")


def find_missing_tags(build_file: Path) -> list[str]:
    """Return simple messages for test rules missing a tags field."""
    lines = build_file.read_text(encoding="utf-8").splitlines()
    missing: list[str] = []
    for index, line in enumerate(lines):
        if not TEST_TARGET_RE.search(line):
            continue
        block = "\n".join(lines[index : min(index + 40, len(lines))])
        if "tags =" not in block:
            missing.append(f"{build_file}:{index + 1}: test target is missing tags")
    return missing


def main() -> int:
    errors: list[str] = []
    for build_file in ROOT.rglob("BUILD.bazel"):
        if "build_tests/_deps" in build_file.as_posix():
            continue
        errors.extend(find_missing_tags(build_file))
    for error in errors:
        print(error)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
