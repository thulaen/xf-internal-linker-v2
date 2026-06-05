#!/usr/bin/env python
"""Guard new native boundaries so they use the project C ABI shape."""

from __future__ import annotations

import argparse
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HEADER_RE = re.compile(r"(?:^|/|\\)include(?:/|\\)xf_[^/\\]+\.h$")
BANNED_DIFF_RE = re.compile(
    r"(pybind11|pybind11_add_module|inline-c-cpp|inline-c|catch_unwind)"
)


def staged_paths() -> list[Path]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACMR"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    return [ROOT / line for line in result.stdout.splitlines() if line]


def added_lines() -> list[tuple[str, str]]:
    result = subprocess.run(
        ["git", "diff", "--cached", "--unified=0"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return []
    path = ""
    lines: list[tuple[str, str]] = []
    for raw in result.stdout.splitlines():
        if raw.startswith("+++ b/"):
            path = raw[6:]
            continue
        if raw.startswith("+") and not raw.startswith("+++"):
            lines.append((path, raw[1:]))
    return lines


def check_header(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    errors: list[str] = []
    if 'extern "C"' not in text:
        errors.append(f"{path}: missing extern \"C\" block")
    if "XF_API" not in text:
        errors.append(f"{path}: missing XF_API export macro")
    if "XF_NOEXCEPT" not in text:
        errors.append(f"{path}: missing XF_NOEXCEPT export marker")
    if "typedef uint32_t xf_status_t;" not in text and "xf_status_t" not in text:
        errors.append(f"{path}: missing xf_status_t status type")
    errors.extend(_check_structs(path, text))
    errors.extend(_check_exports(path, text))
    return errors


def _check_structs(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    for match in re.finditer(r"typedef\s+struct\s+(\w+)\s*\{(?P<body>.*?)\}\s*\w+\s*;", text, re.S):
        body_lines = [
            line.strip()
            for line in match.group("body").splitlines()
            if line.strip() and not line.strip().startswith("//")
        ]
        if body_lines[:2] != ["uint32_t abi_size;", "uint32_t abi_version;"]:
            errors.append(
                f"{path}: struct {match.group(1)} must start with "
                "uint32_t abi_size; uint32_t abi_version;"
            )
    return errors


def _check_exports(path: Path, text: str) -> list[str]:
    errors: list[str] = []
    export_text = "\n".join(
        line for line in text.splitlines() if not line.strip().startswith("#")
    )
    for match in re.finditer(r"XF_API\s+([^;]+);", export_text, re.S):
        declaration = " ".join(match.group(1).split())
        name_match = re.search(r"\b(xf_[a-zA-Z0-9_]+)\s*\(", declaration)
        if not name_match:
            errors.append(f"{path}: exported function must use xf_ prefix: {declaration}")
        if "XF_NOEXCEPT" not in declaration:
            errors.append(f"{path}: exported function missing XF_NOEXCEPT: {declaration}")
    return errors


def check_added_banned_lines() -> list[str]:
    errors: list[str] = []
    for path, line in added_lines():
        if BANNED_DIFF_RE.search(line):
            errors.append(f"{path}: banned native-boundary token added: {line.strip()}")
    return errors


def check_paths(paths: list[Path]) -> list[str]:
    errors: list[str] = []
    for path in paths:
        rel = _display_path(path)
        if HEADER_RE.search(rel.replace("\\", "/")) and path.exists():
            errors.extend(check_header(path))
    return errors


def _display_path(path: Path) -> str:
    if not path.is_absolute():
        return str(path)
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--check-files", nargs="*", type=Path)
    args = parser.parse_args(argv)

    paths = args.check_files if args.check_files is not None else staged_paths()
    errors = check_paths(paths)
    if args.check_files is None:
        errors.extend(check_added_banned_lines())
    for error in errors:
        print(f"FAIL check-c-abi-conformance: {error}", file=sys.stderr)
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
