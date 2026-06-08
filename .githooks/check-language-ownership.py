#!/usr/bin/env python3
"""Block code written in the wrong language — hard block.

The repo assigns each kind of work to the language that owns it:
  * C++   — native hot-path compute (MinHash / LSH / fingerprinting).
  * Go    — transport, service wiring, HTTP/RPC servers. Never owns Postgres.
  * Python/Django — orchestration and domain logic.

This gate catches the most common ownership violations as IMPLEMENTATIONS
(not imports — that boundary is check-no-cross-language-import.py's job, and
Rust justification is check-rust-mandate.py's job). It is deliberately
conservative so it does not block legitimate orchestration code.

What it flags:
  1. Python that reimplements MinHash / LSH / SimHash instead of calling the
     C++ papertrail_dedup extension.
  2. Python that stands up an HTTP server (Flask / FastAPI / aiohttp /
     http.server) — transport belongs in a Go service.
  3. A Go service file that owns a Postgres table (gorm/db struct tags,
     CREATE TABLE, pgx/postgres driver) — Go services never own tables.

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
_PY_HTTP_SERVER_RE = re.compile(
    r"\bFlask\s*\(|\bFastAPI\s*\(|aiohttp\.web\.Application|http\.server|"
    r"socketserver\.TCPServer|\bHTTPServer\s*\(|make_server\s*\(",
)
_GO_PG_RE = re.compile(
    r'gorm:"|`db:"|CREATE\s+TABLE|sql\.Open\(\s*"postgres"|pgx\.Connect|'
    r'pgxpool\.|lib/pq',
    re.I,
)
_GO_COMMENT_RE = re.compile(r"//.*?$|/\*.*?\*/", re.S | re.M)


def _strip_go_comments(text: str) -> str:
    return _GO_COMMENT_RE.sub("", text)


def _is_test_or_generated(path: str) -> bool:
    return bool(
        re.search(r"(^|/)(tests?/|test_|tests_)|_test\.(py|go)$|/api/gen/|"
                  r"_pb2|\.pb\.go$|/migrations/", path)
    )


def _scan_python(path: str, text: str) -> list[str]:
    out: list[str] = []
    if _MINHASH_NAME_RE.search(text) and not _DEDUP_IMPORT_RE.search(text):
        out.append(
            f"{path}: looks like a MinHash/LSH reimplementation in Python. "
            "Hot-path dedup belongs in the C++ papertrail_dedup extension; "
            "call it instead of reimplementing."
        )
    if _PY_HTTP_SERVER_RE.search(text) and not re.search(r"/(views|urls|asgi|wsgi)\.py$", path):
        out.append(
            f"{path}: stands up an HTTP server in Python. Transport/serving "
            "belongs in a Go service (services/<name>/), not Python."
        )
    return out


def _scan_go(path: str, text: str) -> list[str]:
    if not path.startswith("services/"):
        return []
    if _GO_PG_RE.search(_strip_go_comments(text)):
        return [
            f"{path}: a Go service appears to own a Postgres table "
            "(gorm/db tags, CREATE TABLE, or a postgres driver). Go services "
            "never own tables — that belongs in a Django model."
        ]
    return []


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
        elif norm.endswith(".go"):
            violations.extend(_scan_go(norm, text))
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
        if line.strip().endswith((".py", ".go"))
    ]


def _fail(violations: list[str]) -> int:
    sys.stderr.write(
        "\nFAIL check-language-ownership: code is written in the wrong language.\n"
        "WHY: each kind of work has an owning language (C++ for hot-path "
        "compute, Go for transport, Python for orchestration and domain "
        "logic). The flagged code crosses that boundary.\n"
        "UNBLOCK: move the logic to its owning language and call it from "
        "Python, or — if this is a false positive — file it via "
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
