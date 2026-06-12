#!/usr/bin/env python3
"""Block code written in the wrong language — hard block.

The repo is Python + Rust ONLY. Each kind of work has an owning language:
  * Rust  — native hot-path compute (MinHash / LSH / fingerprinting), exposed
            to Python through PyO3 extensions.
  * Python/Django — orchestration, domain logic, and web serving (Django IS the
            web/transport layer).

This gate catches the most common ownership violation as an IMPLEMENTATION
(not imports — that boundary is check-no-cross-language-import.py's job, and
Rust justification is check-rust-mandate.py's job). It is deliberately
conservative so it does not block legitimate orchestration code.

What it flags:
  1. Python that reimplements MinHash / LSH / SimHash instead of calling the
     Rust papertrail_dedup extension.

The helper ``scan_paths(paths)`` is exposed so tests never touch the git index.
"""

from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]

_MINHASH_NAME_RE = re.compile(r"min_?hash|simhash|lsh_bands|shingle_hash|jaccard_bands", re.I)
_DEDUP_IMPORT_RE = re.compile(r"papertrail_dedup|import\s+\w*dedup\w*", re.I)


def _is_test_or_generated(path: str) -> bool:
    return bool(
        re.search(r"(^|/)(tests?/|test_|tests_)|_test\.py$|/api/gen/|"
                  r"_pb2|/migrations/", path)
    )


def _scan_python(path: str, text: str) -> list[str]:
    out: list[str] = []
    if _MINHASH_NAME_RE.search(text) and not _DEDUP_IMPORT_RE.search(text):
        out.append(
            f"{path}: looks like a MinHash/LSH reimplementation in Python. "
            "Hot-path dedup belongs in the Rust papertrail_dedup extension; "
            "call it instead of reimplementing."
        )
    return out


def scan_paths(paths: list[str]) -> list[str]:
    violations: list[str] = []
    for path in paths:
        norm = path.replace("\\", "/")
        if _is_test_or_generated(norm):
            continue
        full = REPO_ROOT / norm
        try:
            text = full.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if norm.endswith(".py") and norm.startswith("backend/"):
            violations.extend(_scan_python(norm, text))
    return violations


def _staged_files() -> list[str]:
    try:
        out = subprocess.check_output(
            ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
            cwd=REPO_ROOT, text=True, encoding="utf-8", errors="replace",
        )
    except (subprocess.CalledProcessError, FileNotFoundError):
        return []
    return [
        line.strip() for line in out.splitlines()
        if line.strip().endswith(".py")
    ]


def _fail(violations: list[str]) -> int:
    sys.stderr.write(
        "\nFAIL check-language-ownership: code is written in the wrong language.\n"
        "WHY: the repo is Python + Rust only. Hot-path compute belongs in Rust "
        "extensions; orchestration, domain logic, and web serving belong in "
        "Python/Django. The flagged code crosses that boundary.\n"
        "UNBLOCK: move the hot-path logic into the Rust extension and call it "
        "from Python, or — if this is a false positive — file it via "
        "`manage.py report_hook_false_positive --hook check-language-ownership`.\n\n"
        + "\n".join(f"  {v}" for v in violations) + "\n"
    )
    return 1


def main() -> int:
    violations = scan_paths(_staged_files())
    if violations:
        return _fail(violations)
    return 0


if __name__ == "__main__":
    sys.exit(main())
